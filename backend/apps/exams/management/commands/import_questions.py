from django.conf import settings
from django.core.management.base import BaseCommand

from apps.exams.importer import import_questions_from_base


class Command(BaseCommand):
    help = "Import tagged exam questions from PDF files under base/<subject>/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-dir",
            default=str(settings.BASE_QUESTIONS_DIR),
            help="Path to the root base directory.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate files without writing new questions.",
        )

    def handle(self, *args, **options):
        summary = import_questions_from_base(options["base_dir"], dry_run=options["dry_run"])

        self.stdout.write(self.style.SUCCESS("Import finished"))
        self.stdout.write(f"Subjects found: {summary.subjects_found}")
        self.stdout.write(f"PDF files found: {summary.files_found}")
        self.stdout.write(f"Questions imported: {summary.imported_questions}")
        self.stdout.write(f"Duplicates skipped: {summary.duplicate_questions}")
        self.stdout.write(f"Invalid questions skipped: {summary.skipped_questions}")

        if summary.errors:
            self.stdout.write(self.style.WARNING("Errors:"))
            for message in summary.errors:
                self.stdout.write(f"- {message}")
