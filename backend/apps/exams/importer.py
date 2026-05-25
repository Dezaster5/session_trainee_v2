import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import AnswerVariant, ImportRun, LiveCodingTask, Question, Subject, Topic


logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"<\s*(question|variant|variantright)\s*>", re.IGNORECASE)
CLOSING_TAG_RE = re.compile(r"</\s*(question|variant|variantright)\s*>", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class ImportSummary:
    subjects_found: int = 0
    files_found: int = 0
    imported_questions: int = 0
    duplicate_questions: int = 0
    skipped_questions: int = 0
    imported_live_coding_tasks: int = 0
    duplicate_live_coding_tasks: int = 0
    skipped_live_coding_tasks: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "subjects_found": self.subjects_found,
            "files_found": self.files_found,
            "imported_questions": self.imported_questions,
            "duplicate_questions": self.duplicate_questions,
            "skipped_questions": self.skipped_questions,
            "imported_live_coding_tasks": self.imported_live_coding_tasks,
            "duplicate_live_coding_tasks": self.duplicate_live_coding_tasks,
            "skipped_live_coding_tasks": self.skipped_live_coding_tasks,
            "errors": self.errors,
        }


def normalize_text(value):
    value = CLOSING_TAG_RE.sub(" ", value or "")
    return WHITESPACE_RE.sub(" ", value).strip()


def normalize_code_block(value):
    value = (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return "\n".join(line.rstrip() for line in value.splitlines())


def subject_name_from_dir(value):
    normalized = normalize_text(str(value).replace("_", " "))
    return normalized.title() if normalized else str(value)


def stable_slug(value, fallback="item"):
    return slugify(normalize_text(value))[:220] or fallback


def parse_json_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return bool(value)


def topic_title_from_json(item, default="General"):
    topic = normalize_text(item.get("topic") or default)
    subtopic = normalize_text(item.get("subtopic") or "")
    if subtopic and subtopic.casefold() != topic.casefold():
        return f"{topic} · {subtopic}"
    return topic or default


def source_relative_path(path, base_path=None):
    try:
        return str(path.relative_to(base_path)) if base_path else str(path)
    except ValueError:
        return str(path)


def extract_pdf_text(path):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to parse PDF question bases") from exc

    chunks = []
    with fitz.open(path) as document:
        for page in document:
            chunks.append(page.get_text("text"))
    return "\n".join(chunks)


def parse_tagged_questions(raw_text):
    matches = list(TAG_RE.finditer(raw_text or ""))
    questions = []
    current = None

    for index, match in enumerate(matches):
        tag = match.group(1).lower()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        content = normalize_text(raw_text[match.end() : next_start])

        if tag == "question":
            if current:
                questions.append(current)
            current = {"text": content, "variants": []}
            continue

        if current is None:
            continue

        current["variants"].append(
            {
                "text": content,
                "is_correct": tag == "variantright",
            }
        )

    if current:
        questions.append(current)

    return [question for question in questions if question.get("text")]


def question_hash(subject_slug, question):
    payload = {
        "subject": subject_slug,
        "text": normalize_text(question["text"]).casefold(),
        "variants": sorted(
            [
                {
                    "text": normalize_text(variant["text"]).casefold(),
                    "is_correct": bool(variant["is_correct"]),
                }
                for variant in question["variants"]
            ],
            key=lambda item: (item["text"], item["is_correct"]),
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def json_question_hash(subject_slug, topic_slug, question):
    external_id = normalize_text(question.get("external_id") or question.get("id") or "")
    if external_id:
        payload = {
            "subject": subject_slug,
            "external_id": external_id.casefold(),
            "kind": "json-question",
        }
    else:
        payload = {
            "subject": subject_slug,
            "topic": topic_slug,
            "text": normalize_text(question["text"]).casefold(),
            "variants": sorted(
                [
                    {
                        "text": normalize_text(variant["text"]).casefold(),
                        "is_correct": bool(variant["is_correct"]),
                    }
                    for variant in question["variants"]
                ],
                key=lambda item: (item["text"], item["is_correct"]),
            ),
            "kind": "json-question",
        }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def live_coding_hash(subject_slug, topic_slug, task):
    external_id = normalize_text(task.get("external_id") or task.get("id") or "")
    if external_id:
        payload = {
            "subject": subject_slug,
            "external_id": external_id.casefold(),
            "kind": "live-coding",
        }
    else:
        payload = {
            "subject": subject_slug,
            "topic": topic_slug,
            "prompt": normalize_text(task["prompt"]).casefold(),
            "language": normalize_text(task["language"]).casefold(),
            "kind": "live-coding",
        }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_json_questions(data):
    raw_questions = data.get("questions") if isinstance(data, dict) else None
    if raw_questions is None:
        return []
    if not isinstance(raw_questions, list):
        raise ValueError("JSON field 'questions' must be a list")

    parsed = []
    for item in raw_questions:
        if not isinstance(item, dict):
            parsed.append({"text": "", "variants": [], "error": "question item must be an object"})
            continue

        correct_option_id = normalize_text(item.get("correct_option_id") or "").casefold()
        variants = []
        for order, option in enumerate(item.get("options") or []):
            if isinstance(option, dict):
                option_id = normalize_text(option.get("id") or "").casefold()
                text = normalize_text(option.get("text") or option.get("value") or "")
                is_correct = parse_json_bool(option.get("is_correct")) or bool(correct_option_id and option_id == correct_option_id)
            else:
                text = normalize_text(option)
                is_correct = False
            variants.append({"text": text, "is_correct": is_correct, "order": order})

        parsed.append(
            {
                "external_id": normalize_text(item.get("id") or ""),
                "text": normalize_text(item.get("question") or item.get("text") or item.get("prompt") or ""),
                "variants": variants,
                "topic_title": topic_title_from_json(item),
                "difficulty": normalize_text(item.get("difficulty") or ""),
                "explanation": normalize_text(item.get("explanation") or item.get("correct_answer") or ""),
                "raw": item,
            }
        )
    return parsed


def parse_json_live_coding(data):
    raw_tasks = data.get("liveCoding") if isinstance(data, dict) else None
    if raw_tasks is None:
        return []
    if not isinstance(raw_tasks, list):
        raise ValueError("JSON field 'liveCoding' must be a list")

    parsed = []
    for item in raw_tasks:
        if not isinstance(item, dict):
            parsed.append({"prompt": "", "expected_solution": "", "error": "liveCoding item must be an object"})
            continue

        checking_method = item.get("checking_method") if isinstance(item.get("checking_method"), dict) else {}
        prompt = normalize_text(item.get("task") or item.get("prompt") or item.get("question") or "")
        language = normalize_text(item.get("expected_solution_language") or item.get("language") or "text")
        parsed.append(
            {
                "external_id": normalize_text(item.get("id") or ""),
                "title": normalize_text(item.get("title") or prompt[:120] or "Live coding task"),
                "prompt": prompt,
                "language": language or "text",
                "expected_solution": normalize_code_block(item.get("expected_solution") or ""),
                "check_type": normalize_text(item.get("check_type") or checking_method.get("mode") or "similarity"),
                "difficulty": normalize_text(item.get("difficulty") or ""),
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "topic_title": topic_title_from_json(item),
                "raw": item,
            }
        )
    return parsed


def validate_question(question, exact_variant_count=None):
    variants = [variant for variant in question.get("variants", []) if variant.get("text")]
    correct_count = sum(1 for variant in variants if variant.get("is_correct"))
    normalized_variants = [normalize_text(variant["text"]).casefold() for variant in variants]

    if not question.get("text"):
        return False, "empty question text"
    if exact_variant_count is not None and len(variants) != exact_variant_count:
        return False, f"question must have exactly {exact_variant_count} variants, found {len(variants)}"
    if len(variants) < 2:
        return False, "question has less than two variants"
    if correct_count != 1:
        return False, f"question must have exactly one right variant, found {correct_count}"
    if len(normalized_variants) != len(set(normalized_variants)):
        return False, "question has duplicated answer variants"
    return True, ""


def validate_live_coding_task(task):
    if not task.get("prompt"):
        return False, "empty live coding prompt"
    if not task.get("expected_solution"):
        return False, "empty expected solution"
    if not task.get("language"):
        return False, "empty language"
    return True, ""


def get_or_create_topic(subject, title, topic_type, order):
    slug = stable_slug(title, fallback=f"{topic_type}-{order}")
    topic, _created = Topic.objects.get_or_create(
        subject=subject,
        slug=slug,
        type=topic_type,
        defaults={
            "title": title,
            "order": order,
        },
    )
    changed = False
    if topic.title != title:
        topic.title = title
        changed = True
    if topic.order != order:
        topic.order = order
        changed = True
    if changed:
        topic.save(update_fields=["title", "order", "updated_at"])
    return topic


def import_questions_from_json_file(path, subject, summary, base_path=None, dry_run=False):
    path = Path(path)
    subject_slug = subject.slug if subject else stable_slug(path.parent.name)
    topic_orders = {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        parsed_questions = parse_json_questions(data)
        parsed_tasks = parse_json_live_coding(data)
        logger.info("Parsed %s theory questions and %s live coding tasks from %s", len(parsed_questions), len(parsed_tasks), path)
    except Exception as exc:
        message = f"{path}: {exc}"
        logger.exception("Failed to parse JSON %s", path)
        summary.errors.append(message)
        return

    source_file = source_relative_path(path, base_path)

    for index, parsed_question in enumerate(parsed_questions, start=1):
        if parsed_question.get("error"):
            summary.skipped_questions += 1
            summary.errors.append(f"{path} question #{index}: {parsed_question['error']}")
            continue

        is_valid, reason = validate_question(parsed_question, exact_variant_count=4)
        if not is_valid:
            summary.skipped_questions += 1
            summary.errors.append(f"{path} question #{index}: {reason}")
            continue

        topic_title = parsed_question["topic_title"]
        topic_slug = stable_slug(topic_title)
        topic_orders.setdefault((Topic.TYPE_THEORY, topic_slug), len(topic_orders) + 1)
        digest = json_question_hash(subject_slug, topic_slug, parsed_question)

        if dry_run:
            if Question.objects.filter(hash=digest).exists():
                summary.duplicate_questions += 1
            else:
                summary.imported_questions += 1
            continue

        topic = get_or_create_topic(
            subject=subject,
            title=topic_title,
            topic_type=Topic.TYPE_THEORY,
            order=topic_orders[(Topic.TYPE_THEORY, topic_slug)],
        )

        try:
            with transaction.atomic():
                existing = Question.objects.filter(hash=digest).first()
                if existing:
                    existing.subject = subject
                    existing.topic = topic
                    existing.text = normalize_text(parsed_question["text"])
                    existing.difficulty = parsed_question.get("difficulty") or None
                    existing.explanation = parsed_question.get("explanation") or None
                    existing.import_format = Question.FORMAT_JSON
                    existing.source_file = source_file
                    existing.save(
                        update_fields=[
                            "subject",
                            "topic",
                            "text",
                            "difficulty",
                            "explanation",
                            "import_format",
                            "source_file",
                            "updated_at",
                        ]
                    )
                    existing.variants.all().delete()
                    question = existing
                    summary.duplicate_questions += 1
                else:
                    question = Question.objects.create(
                        subject=subject,
                        topic=topic,
                        text=normalize_text(parsed_question["text"]),
                        difficulty=parsed_question.get("difficulty") or None,
                        explanation=parsed_question.get("explanation") or None,
                        import_format=Question.FORMAT_JSON,
                        source_file=source_file,
                        hash=digest,
                    )
                    summary.imported_questions += 1

                AnswerVariant.objects.bulk_create(
                    [
                        AnswerVariant(
                            question=question,
                            text=normalize_text(variant["text"]),
                            is_correct=variant["is_correct"],
                            order=order,
                        )
                        for order, variant in enumerate(parsed_question["variants"])
                        if variant.get("text")
                    ]
                )
        except IntegrityError as exc:
            summary.duplicate_questions += 1
            summary.errors.append(f"{path} question #{index}: duplicate or constraint violation: {exc}")
            continue

    for index, parsed_task in enumerate(parsed_tasks, start=1):
        if parsed_task.get("error"):
            summary.skipped_live_coding_tasks += 1
            summary.errors.append(f"{path} liveCoding #{index}: {parsed_task['error']}")
            continue

        is_valid, reason = validate_live_coding_task(parsed_task)
        if not is_valid:
            summary.skipped_live_coding_tasks += 1
            summary.errors.append(f"{path} liveCoding #{index}: {reason}")
            continue

        topic_title = parsed_task["topic_title"]
        topic_slug = stable_slug(topic_title)
        topic_orders.setdefault((Topic.TYPE_LIVE_CODING, topic_slug), len(topic_orders) + 1)
        digest = live_coding_hash(subject_slug, topic_slug, parsed_task)

        if dry_run:
            if LiveCodingTask.objects.filter(hash=digest).exists():
                summary.duplicate_live_coding_tasks += 1
            else:
                summary.imported_live_coding_tasks += 1
            continue

        topic = get_or_create_topic(
            subject=subject,
            title=topic_title,
            topic_type=Topic.TYPE_LIVE_CODING,
            order=topic_orders[(Topic.TYPE_LIVE_CODING, topic_slug)],
        )

        task_values = {
            "subject": subject,
            "topic": topic,
            "title": parsed_task["title"],
            "prompt": parsed_task["prompt"],
            "language": parsed_task["language"],
            "expected_solution": parsed_task["expected_solution"],
            "check_type": parsed_task["check_type"] or "similarity",
            "difficulty": parsed_task.get("difficulty") or None,
            "tags": parsed_task.get("tags") or [],
            "source_file": source_file,
        }

        try:
            task, created = LiveCodingTask.objects.update_or_create(
                hash=digest,
                defaults=task_values,
            )
        except IntegrityError as exc:
            summary.duplicate_live_coding_tasks += 1
            summary.errors.append(f"{path} liveCoding #{index}: duplicate or constraint violation: {exc}")
            continue

        if created:
            summary.imported_live_coding_tasks += 1
        else:
            summary.duplicate_live_coding_tasks += 1


def import_questions_from_base(base_dir, dry_run=False):
    base_path = Path(base_dir)
    summary = ImportSummary()
    run = ImportRun.objects.create(base_dir=str(base_path))
    seen_hashes = set()

    try:
        if not base_path.exists():
            raise FileNotFoundError(f"Base directory does not exist: {base_path}")

        subject_dirs = sorted(path for path in base_path.iterdir() if path.is_dir())
        summary.subjects_found = len(subject_dirs)
        logger.info("Found %s subject directories in %s", summary.subjects_found, base_path)

        for subject_dir in subject_dirs:
            subject_slug = slugify(subject_dir.name) or subject_dir.name.lower().replace(" ", "-")
            subject_name = subject_name_from_dir(subject_dir.name)
            pdf_files = sorted(subject_dir.glob("*.pdf"))
            json_files = sorted(subject_dir.glob("*.json"))
            summary.files_found += len(pdf_files) + len(json_files)

            subject = None
            if not dry_run:
                subject, _ = Subject.objects.get_or_create(
                    slug=subject_slug,
                    defaults={
                        "name": subject_name,
                        "source_path": str(subject_dir),
                    },
                )
                Subject.objects.filter(pk=subject.pk).update(
                    name=subject_name,
                    source_path=str(subject_dir),
                    imported_at=timezone.now(),
                )

            for pdf_file in pdf_files:
                try:
                    raw_text = extract_pdf_text(pdf_file)
                    parsed_questions = parse_tagged_questions(raw_text)
                    logger.info("Parsed %s questions from %s", len(parsed_questions), pdf_file)
                except Exception as exc:
                    message = f"{pdf_file}: {exc}"
                    logger.exception("Failed to parse %s", pdf_file)
                    summary.errors.append(message)
                    continue

                for index, parsed_question in enumerate(parsed_questions, start=1):
                    is_valid, reason = validate_question(parsed_question)
                    if not is_valid:
                        summary.skipped_questions += 1
                        summary.errors.append(f"{pdf_file} question #{index}: {reason}")
                        continue

                    digest = question_hash(subject_slug, parsed_question)
                    if digest in seen_hashes or Question.objects.filter(hash=digest).exists():
                        summary.duplicate_questions += 1
                        continue
                    seen_hashes.add(digest)

                    if dry_run:
                        summary.imported_questions += 1
                        continue

                    try:
                        with transaction.atomic():
                            question = Question.objects.create(
                                subject=subject,
                                text=normalize_text(parsed_question["text"]),
                                import_format=Question.FORMAT_PDF,
                                source_file=source_relative_path(pdf_file, base_path),
                                hash=digest,
                            )
                            AnswerVariant.objects.bulk_create(
                                [
                                    AnswerVariant(
                                        question=question,
                                        text=normalize_text(variant["text"]),
                                        is_correct=variant["is_correct"],
                                        order=order,
                                    )
                                    for order, variant in enumerate(parsed_question["variants"])
                                    if variant.get("text")
                                ]
                            )
                    except IntegrityError as exc:
                        summary.duplicate_questions += 1
                        summary.errors.append(f"{pdf_file} question #{index}: duplicate or constraint violation: {exc}")
                        continue
                    summary.imported_questions += 1

            for json_file in json_files:
                import_questions_from_json_file(
                    json_file,
                    subject,
                    summary,
                    base_path=base_path,
                    dry_run=dry_run,
                )

        run.status = ImportRun.STATUS_SUCCESS
    except Exception as exc:
        logger.exception("Question import failed")
        run.status = ImportRun.STATUS_FAILED
        summary.errors.append(str(exc))
    finally:
        run.subjects_found = summary.subjects_found
        run.files_found = summary.files_found
        run.imported_questions = summary.imported_questions
        run.duplicate_questions = summary.duplicate_questions
        run.skipped_questions = summary.skipped_questions
        run.imported_live_coding_tasks = summary.imported_live_coding_tasks
        run.duplicate_live_coding_tasks = summary.duplicate_live_coding_tasks
        run.skipped_live_coding_tasks = summary.skipped_live_coding_tasks
        run.errors = summary.errors
        run.finished_at = timezone.now()
        run.save()

    return summary
