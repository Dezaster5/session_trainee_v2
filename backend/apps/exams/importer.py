import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    AnswerVariant,
    ImportRun,
    LiveCodingTask,
    Question,
    Subject,
    TestSession,
    Topic,
    UserSubjectStats,
)


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


def subject_metadata_from_json(data):
    if not isinstance(data, dict):
        return "", ""

    raw_subject = data.get("subject")
    raw_slug = data.get("slug")

    if isinstance(raw_subject, dict):
        subject_name = raw_subject.get("name") or raw_subject.get("title") or ""
        subject_slug = raw_slug or raw_subject.get("slug") or ""
    else:
        subject_name = raw_subject or ""
        subject_slug = raw_slug or ""

    return normalize_text(str(subject_name)) if subject_name else "", normalize_text(str(subject_slug)) if subject_slug else ""


def subject_metadata_from_json_files(json_files):
    for json_file in json_files:
        try:
            data = json.loads(Path(json_file).read_text(encoding="utf-8"))
        except Exception:
            continue

        subject_name, subject_slug = subject_metadata_from_json(data)
        if subject_name or subject_slug:
            return subject_name, subject_slug
    return "", ""


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


def resolve_image_path(image, json_path, base_path=None):
    """Normalize a per-question image reference to a path relative to the base dir.

    JSON stores image paths relative to the subject folder (e.g. ``images/EIE-Q0044.png``).
    We persist the path relative to ``BASE_QUESTIONS_DIR`` (e.g.
    ``Economics_and_Industrial_Engineering/images/EIE-Q0044.png``) so a single media
    endpoint can serve every subject without extra lookups.
    """
    if not isinstance(image, str):
        return None
    cleaned = image.strip().replace("\\", "/").lstrip("/")
    if not cleaned:
        return None
    candidate = Path(json_path).parent / cleaned
    if base_path is not None:
        try:
            return candidate.relative_to(base_path).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix()


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
    provided_hash = normalize_text(question.get("hash") or "")
    if provided_hash:
        return provided_hash[:64]

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
    provided_hash = normalize_text(task.get("hash") or "")
    if provided_hash:
        return provided_hash[:64]

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
                "formula": normalize_text(item.get("formula") or ""),
                "image": item.get("image") if isinstance(item.get("image"), str) else "",
                "source_file": normalize_text(item.get("source_file") or ""),
                "hash": normalize_text(item.get("hash") or ""),
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
                "source_file": normalize_text(item.get("source_file") or ""),
                "hash": normalize_text(item.get("hash") or ""),
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


def normalized_answer_variants(variants):
    return [
        {
            "text": normalize_text(variant["text"]),
            "is_correct": bool(variant["is_correct"]),
            "order": order,
        }
        for order, variant in enumerate(variants)
        if variant.get("text")
    ]


def sync_answer_variants(question, variants):
    incoming = normalized_answer_variants(variants)
    existing_by_text = {
        normalize_text(variant.text).casefold(): variant
        for variant in question.variants.all()
    }
    kept_ids = []
    correct_variant = None

    # Clear the single-correct-answer constraint first, then restore the new
    # correct variant after inserts/updates are done.
    AnswerVariant.objects.filter(question=question, is_correct=True).update(is_correct=False)

    for item in incoming:
        key = item["text"].casefold()
        variant = existing_by_text.get(key)
        if variant is None:
            variant = AnswerVariant.objects.create(
                question=question,
                text=item["text"],
                is_correct=False,
                order=item["order"],
            )
        else:
            changed_fields = []
            if variant.text != item["text"]:
                variant.text = item["text"]
                changed_fields.append("text")
            if variant.order != item["order"]:
                variant.order = item["order"]
                changed_fields.append("order")
            if variant.is_correct:
                variant.is_correct = False
                changed_fields.append("is_correct")
            if changed_fields:
                variant.save(update_fields=changed_fields)

        kept_ids.append(variant.id)
        if item["is_correct"]:
            correct_variant = variant

    question.variants.exclude(id__in=kept_ids).delete()
    if correct_variant:
        AnswerVariant.objects.filter(pk=correct_variant.pk).update(is_correct=True)


def get_or_create_subject(subject_slug, subject_name, folder_slug, subject_dir):
    subject = Subject.objects.filter(slug=subject_slug).first()
    if subject is None and folder_slug != subject_slug:
        subject = Subject.objects.filter(slug=folder_slug).first()
        if subject:
            subject.slug = subject_slug

    if subject is None:
        return Subject.objects.create(
            slug=subject_slug,
            name=subject_name,
            source_path=str(subject_dir),
            imported_at=timezone.now(),
        )

    subject.name = subject_name
    subject.source_path = str(subject_dir)
    subject.imported_at = timezone.now()
    subject.save(update_fields=["slug", "name", "source_path", "imported_at", "updated_at"])
    return subject


def json_requests_subject_replace(data):
    """Return True when a JSON base explicitly asks to replace the old subject base.

    The new base sets ``metadata.replace_subject = true`` to signal that any older,
    differently hashed questions for the same subject must be removed before import.
    """
    if not isinstance(data, dict):
        return False
    if parse_json_bool(data.get("replace_subject")):
        return True
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        if parse_json_bool(metadata.get("replace_subject")):
            return True
        if parse_json_bool(metadata.get("replaces_previous")):
            return True
    return False


def prune_replaced_subject_questions(subject, keep_hashes):
    """Remove stale questions of a subject that are not part of the incoming base.

    Questions whose hash is in ``keep_hashes`` are preserved so repeated imports stay
    idempotent and keep user progress attached. Only when something is actually removed
    do we also clear now-inconsistent theory sessions and subject stats. Live coding data
    is left untouched (the subject keeps its tasks if it has any).
    """
    stale = Question.objects.filter(subject=subject).exclude(hash__in=keep_hashes)
    removed = stale.count()
    if not removed:
        return 0

    # Deleting the questions cascades AnswerVariant, TestSessionQuestion, TestAnswer and
    # UserQuestionProgress rows that referenced the removed (old) questions.
    stale.delete()
    TestSession.objects.filter(subject=subject).delete()
    if not LiveCodingTask.objects.filter(subject=subject).exists():
        UserSubjectStats.objects.filter(subject=subject).delete()
    return removed


def find_existing_question_for_json_update(subject, digest, parsed_question, incoming_hashes=None):
    existing = Question.objects.filter(hash=digest).first()
    if existing:
        return existing

    # Legacy imports for JSON files used generated hashes before per-question
    # JSON hashes were supported. Match by subject and exact text so user
    # progress stays attached when the hash strategy is upgraded.
    queryset = Question.objects.filter(
        subject=subject,
        import_format=Question.FORMAT_JSON,
        text=normalize_text(parsed_question["text"]),
    )
    if incoming_hashes:
        queryset = queryset.exclude(hash__in=incoming_hashes)
    return queryset.first()


def item_source_file(parsed_item, fallback, use_item_source_file):
    if use_item_source_file and parsed_item.get("source_file"):
        return parsed_item["source_file"]
    return fallback


def filter_json_files_for_replacement(json_files):
    """Use only replacement JSON files when a subject folder contains them.

    This prevents an old JSON base left on a server from being imported again after
    the replacement file has pruned stale questions for the same subject.
    """
    replacement_files = []
    for json_file in json_files:
        try:
            data = json.loads(Path(json_file).read_text(encoding="utf-8"))
        except Exception:
            continue
        if json_requests_subject_replace(data):
            replacement_files.append(json_file)
    return replacement_files or json_files


def import_questions_from_json_file(path, subject, summary, base_path=None, dry_run=False):
    path = Path(path)
    subject_slug = subject.slug if subject else stable_slug(path.parent.name)
    topic_orders = {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        metadata_subject_name, metadata_subject_slug = subject_metadata_from_json(data)
        if metadata_subject_slug:
            subject_slug = stable_slug(metadata_subject_slug, fallback=subject_slug)
        elif metadata_subject_name and not subject:
            subject_slug = stable_slug(metadata_subject_name, fallback=subject_slug)
        raw_top_level_slug = data.get("slug")
        use_item_source_file = isinstance(raw_top_level_slug, str) and bool(normalize_text(raw_top_level_slug))
        parsed_questions = parse_json_questions(data)
        parsed_tasks = parse_json_live_coding(data)
        logger.info("Parsed %s theory questions and %s live coding tasks from %s", len(parsed_questions), len(parsed_tasks), path)
    except Exception as exc:
        message = f"{path}: {exc}"
        logger.exception("Failed to parse JSON %s", path)
        summary.errors.append(message)
        return

    source_file = source_relative_path(path, base_path)
    incoming_question_hashes = set()
    for parsed_question in parsed_questions:
        if parsed_question.get("error"):
            continue
        is_valid, _reason = validate_question(parsed_question, exact_variant_count=4)
        if not is_valid:
            continue
        keep_topic_slug = stable_slug(parsed_question["topic_title"])
        incoming_question_hashes.add(json_question_hash(subject_slug, keep_topic_slug, parsed_question))

    if json_requests_subject_replace(data) and subject is not None and not dry_run:
        removed = prune_replaced_subject_questions(subject, incoming_question_hashes)
        if removed:
            logger.info("replace_subject: removed %s stale questions for %s", removed, subject.slug)

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
        image_path = resolve_image_path(parsed_question.get("image"), path, base_path)

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
                existing = find_existing_question_for_json_update(
                    subject,
                    digest,
                    parsed_question,
                    incoming_hashes=incoming_question_hashes,
                )
                if existing:
                    existing.subject = subject
                    existing.topic = topic
                    existing.text = normalize_text(parsed_question["text"])
                    existing.difficulty = parsed_question.get("difficulty") or None
                    existing.explanation = parsed_question.get("explanation") or None
                    existing.formula = parsed_question.get("formula") or None
                    existing.image = image_path
                    existing.import_format = Question.FORMAT_JSON
                    existing.source_file = item_source_file(parsed_question, source_file, use_item_source_file)
                    existing.hash = digest
                    existing.save(
                        update_fields=[
                            "subject",
                            "topic",
                            "text",
                            "difficulty",
                            "explanation",
                            "formula",
                            "image",
                            "import_format",
                            "source_file",
                            "hash",
                            "updated_at",
                        ]
                    )
                    sync_answer_variants(existing, parsed_question["variants"])
                    summary.duplicate_questions += 1
                else:
                    question = Question.objects.create(
                        subject=subject,
                        topic=topic,
                        text=normalize_text(parsed_question["text"]),
                        difficulty=parsed_question.get("difficulty") or None,
                        explanation=parsed_question.get("explanation") or None,
                        formula=parsed_question.get("formula") or None,
                        image=image_path,
                        import_format=Question.FORMAT_JSON,
                        source_file=item_source_file(parsed_question, source_file, use_item_source_file),
                        hash=digest,
                    )
                    summary.imported_questions += 1

                    AnswerVariant.objects.bulk_create(
                        [
                            AnswerVariant(
                                question=question,
                                text=variant["text"],
                                is_correct=variant["is_correct"],
                                order=variant["order"],
                            )
                            for variant in normalized_answer_variants(parsed_question["variants"])
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
            "source_file": item_source_file(parsed_task, source_file, use_item_source_file),
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
            pdf_files = sorted(subject_dir.glob("*.pdf"))
            json_files = filter_json_files_for_replacement(sorted(subject_dir.glob("*.json")))
            folder_slug = slugify(subject_dir.name) or subject_dir.name.lower().replace(" ", "-")
            folder_name = subject_name_from_dir(subject_dir.name)
            json_subject_name, json_subject_slug = subject_metadata_from_json_files(json_files)
            subject_slug = stable_slug(json_subject_slug, fallback=folder_slug) if json_subject_slug else folder_slug
            subject_name = json_subject_name or folder_name
            summary.files_found += len(pdf_files) + len(json_files)

            subject = None
            if not dry_run:
                subject = get_or_create_subject(
                    subject_slug=subject_slug,
                    subject_name=subject_name,
                    folder_slug=folder_slug,
                    subject_dir=subject_dir,
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
