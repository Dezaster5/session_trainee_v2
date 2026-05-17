import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import AnswerVariant, ImportRun, Question, Subject


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
    errors: list[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "subjects_found": self.subjects_found,
            "files_found": self.files_found,
            "imported_questions": self.imported_questions,
            "duplicate_questions": self.duplicate_questions,
            "skipped_questions": self.skipped_questions,
            "errors": self.errors,
        }


def normalize_text(value):
    value = CLOSING_TAG_RE.sub(" ", value or "")
    return WHITESPACE_RE.sub(" ", value).strip()


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


def validate_question(question):
    variants = [variant for variant in question.get("variants", []) if variant.get("text")]
    correct_count = sum(1 for variant in variants if variant.get("is_correct"))
    normalized_variants = [normalize_text(variant["text"]).casefold() for variant in variants]

    if not question.get("text"):
        return False, "empty question text"
    if len(variants) < 2:
        return False, "question has less than two variants"
    if correct_count != 1:
        return False, f"question must have exactly one right variant, found {correct_count}"
    if len(normalized_variants) != len(set(normalized_variants)):
        return False, "question has duplicated answer variants"
    return True, ""


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
            subject_name = subject_dir.name.replace("_", " ").strip() or subject_dir.name
            pdf_files = sorted(subject_dir.glob("*.pdf"))
            summary.files_found += len(pdf_files)

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
                                source_file=str(pdf_file.relative_to(base_path)),
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
        run.errors = summary.errors
        run.finished_at = timezone.now()
        run.save()

    return summary
