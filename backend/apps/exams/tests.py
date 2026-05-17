from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .importer import import_questions_from_base, parse_tagged_questions, question_hash, validate_question
from .models import AnswerVariant, Question, Subject, TestSession, TestSessionQuestion, UserQuestionProgress, UserSubjectStats
from .serializers import TestSessionStateSerializer
from .services import calculate_points, create_test_session, record_answer, select_questions


User = get_user_model()


class ImportParserTests(TestCase):
    def test_parse_tagged_questions(self):
        raw = """
        <question> What is overfitting?
        <variant> High training error
        <variantright> Good train score and poor validation score
        <variant> Missing data only
        <question> What is regularization?
        <variant> A data split
        <variantright> A constraint that reduces model complexity
        """

        questions = parse_tagged_questions(raw)

        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["text"], "What is overfitting?")
        self.assertEqual(sum(1 for item in questions[0]["variants"] if item["is_correct"]), 1)
        self.assertEqual(
            question_hash("ml", questions[0]),
            question_hash("ml", questions[0]),
        )

    def test_hash_is_stable_when_variant_order_changes(self):
        first = {
            "text": "What is bias?",
            "variants": [
                {"text": "Wrong", "is_correct": False},
                {"text": "Right", "is_correct": True},
            ],
        }
        second = {
            "text": "What is bias?",
            "variants": [
                {"text": "Right", "is_correct": True},
                {"text": "Wrong", "is_correct": False},
            ],
        }

        self.assertEqual(question_hash("ml", first), question_hash("ml", second))

    def test_rejects_duplicate_answer_variants(self):
        is_valid, reason = validate_question(
            {
                "text": "Choose one",
                "variants": [
                    {"text": "Same", "is_correct": True},
                    {"text": "Same", "is_correct": False},
                ],
            }
        )

        self.assertFalse(is_valid)
        self.assertIn("duplicated", reason)

    def test_import_skips_duplicates_across_files_and_repeated_runs(self):
        raw = """
        <question> What is validation?
        <variant> Training only
        <variantright> Measuring quality on held-out data
        <variant> Deployment
        """

        with TemporaryDirectory() as tmp:
            subject_dir = Path(tmp) / "Machine_learning"
            subject_dir.mkdir()
            (subject_dir / "first.pdf").touch()
            (subject_dir / "second.pdf").touch()

            with patch("apps.exams.importer.extract_pdf_text", return_value=raw):
                first = import_questions_from_base(tmp)
                second = import_questions_from_base(tmp)

        self.assertEqual(first.imported_questions, 1)
        self.assertEqual(first.duplicate_questions, 1)
        self.assertEqual(second.imported_questions, 0)
        self.assertEqual(second.duplicate_questions, 2)
        self.assertEqual(Question.objects.count(), 1)


class TestSelectionAndScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="strong-pass-123")
        self.subject = Subject.objects.create(name="Machine Learning", slug="machine-learning")
        self.questions = []
        for index in range(6):
            question = Question.objects.create(
                subject=self.subject,
                text=f"Question {index}",
                source_file="sample.pdf",
                hash=f"hash-{index}",
            )
            AnswerVariant.objects.create(question=question, text="Wrong", order=0)
            AnswerVariant.objects.create(question=question, text="Right", is_correct=True, order=1)
            self.questions.append(question)

    def test_new_mode_returns_unseen_questions(self):
        UserQuestionProgress.objects.create(user=self.user, question=self.questions[0], times_seen=1)

        selected = select_questions(self.user, self.subject, TestSession.MODE_NEW, 5)

        self.assertNotIn(self.questions[0], selected)
        self.assertEqual(len(selected), 5)

    def test_new_mode_returns_empty_when_everything_was_seen(self):
        for question in self.questions:
            UserQuestionProgress.objects.create(user=self.user, question=question, times_seen=1)

        selected = select_questions(self.user, self.subject, TestSession.MODE_NEW, 5)
        session = create_test_session(self.user, self.subject, TestSession.MODE_NEW, 5)

        self.assertEqual(selected, [])
        self.assertIsNone(session)

    def test_mistakes_mode_prioritizes_wrong_questions(self):
        UserQuestionProgress.objects.create(
            user=self.user,
            question=self.questions[2],
            times_seen=3,
            times_wrong=2,
            personal_weight=3.0,
        )

        selected = select_questions(self.user, self.subject, TestSession.MODE_MISTAKES, 1)

        self.assertEqual(selected, [self.questions[2]])

    def test_points_are_capped_per_question(self):
        progress = UserQuestionProgress.objects.create(
            user=self.user,
            question=self.questions[0],
            points_earned=15,
        )

        self.assertEqual(calculate_points(progress, True), 1)
        progress.points_earned = 16
        self.assertEqual(calculate_points(progress, True), 0)
        self.assertEqual(calculate_points(progress, False), -2)

    def test_record_answer_updates_stats(self):
        session = create_test_session(self.user, self.subject, TestSession.MODE_REVIEW_ALL, 1)
        entry = session.session_questions.first()
        correct_variant = entry.question.variants.get(is_correct=True)

        pre_answer_stats = UserSubjectStats.objects.get(user=self.user, subject=self.subject)
        self.assertEqual(pre_answer_stats.unique_questions_seen, 1)
        self.assertEqual(pre_answer_stats.total_answered, 0)

        answer, progress = record_answer(session, entry.question_id, correct_variant.id, time_spent=12)

        stats = UserSubjectStats.objects.get(user=self.user, subject=self.subject)
        self.assertTrue(answer.is_correct)
        self.assertEqual(progress.times_seen, 1)
        self.assertEqual(progress.times_correct, 1)
        self.assertEqual(stats.correct_answers, 1)
        self.assertEqual(stats.unique_questions_seen, 1)

    def test_progress_is_isolated_between_users(self):
        other = User.objects.create_user(username="other", password="strong-pass-123")
        question = self.questions[0]
        correct_variant = question.variants.get(is_correct=True)
        wrong_variant = question.variants.get(is_correct=False)

        first_session = create_test_session(self.user, self.subject, TestSession.MODE_REVIEW_ALL, 1)
        TestSession.objects.filter(pk=first_session.pk).update(total_questions=1)
        first_entry = first_session.session_questions.first()
        if first_entry.question_id != question.id:
            first_entry.question = question
            first_entry.save(update_fields=["question"])
        record_answer(first_session, question.id, correct_variant.id)

        other_session = create_test_session(other, self.subject, TestSession.MODE_REVIEW_ALL, 1)
        TestSession.objects.filter(pk=other_session.pk).update(total_questions=1)
        other_entry = other_session.session_questions.first()
        if other_entry.question_id != question.id:
            other_entry.question = question
            other_entry.save(update_fields=["question"])
        record_answer(other_session, question.id, wrong_variant.id)

        first_progress = UserQuestionProgress.objects.get(user=self.user, question=question)
        other_progress = UserQuestionProgress.objects.get(user=other, question=question)
        self.assertEqual(first_progress.times_correct, 1)
        self.assertEqual(first_progress.times_wrong, 0)
        self.assertEqual(other_progress.times_correct, 0)
        self.assertEqual(other_progress.times_wrong, 1)

    def test_test_session_serializes_variants_in_stable_shuffled_order(self):
        question = Question.objects.create(
            subject=self.subject,
            text="Five variants question",
            source_file="sample.pdf",
            hash="five-variant-hash",
        )
        for index in range(4):
            AnswerVariant.objects.create(question=question, text=f"Wrong {index}", order=index)
        AnswerVariant.objects.create(question=question, text="Correct", is_correct=True, order=4)
        session = TestSession.objects.create(
            user=self.user,
            subject=self.subject,
            mode=TestSession.MODE_REVIEW_ALL,
            total_questions=1,
        )
        TestSessionQuestion.objects.create(session=session, question=question, order=1)

        original_ids = list(question.variants.values_list("id", flat=True))
        first_payload = TestSessionStateSerializer(session).data
        second_payload = TestSessionStateSerializer(session).data
        shuffled_ids = [variant["id"] for variant in first_payload["current_question"]["question"]["variants"]]

        self.assertEqual(set(shuffled_ids), set(original_ids))
        self.assertEqual(
            shuffled_ids,
            [variant["id"] for variant in second_payload["current_question"]["question"]["variants"]],
        )
        self.assertNotEqual(shuffled_ids, original_ids)


class ApiEdgeCaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="api-user", password="strong-pass-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.subject = Subject.objects.create(name="ML", slug="ml")
        self.question = Question.objects.create(
            subject=self.subject,
            text="Question",
            source_file="sample.pdf",
            hash="api-hash",
        )
        self.wrong = AnswerVariant.objects.create(question=self.question, text="Wrong", order=0)
        self.right = AnswerVariant.objects.create(question=self.question, text="Right", is_correct=True, order=1)

    def test_start_test_rejects_invalid_question_count(self):
        response = self.client.post(
            "/api/tests/start/",
            {"subject_id": self.subject.id, "mode": "random", "question_count": "many"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TestSession.objects.count(), 0)

    def test_start_test_with_empty_subject_does_not_create_session(self):
        empty = Subject.objects.create(name="Empty", slug="empty")

        response = self.client.post(
            "/api/tests/start/",
            {"subject_id": empty.id, "mode": "random", "question_count": "10"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(TestSession.objects.filter(subject=empty).count(), 0)

    def test_duplicate_answer_is_rejected(self):
        session = create_test_session(self.user, self.subject, TestSession.MODE_REVIEW_ALL, 1)
        entry = session.session_questions.first()
        variant = entry.question.variants.get(is_correct=True)

        first = self.client.post(
            f"/api/tests/{session.id}/answer/",
            {"question_id": entry.question_id, "selected_variant_id": variant.id},
            format="json",
        )
        second = self.client.post(
            f"/api/tests/{session.id}/answer/",
            {"question_id": entry.question_id, "selected_variant_id": variant.id},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)

    def test_leaderboard_excludes_users_without_answers(self):
        viewer = User.objects.create_user(username="viewer", password="strong-pass-123")
        UserSubjectStats.objects.create(user=viewer, subject=self.subject, unique_questions_seen=1)

        session = create_test_session(self.user, self.subject, TestSession.MODE_REVIEW_ALL, 1)
        entry = session.session_questions.first()
        variant = entry.question.variants.get(is_correct=True)
        record_answer(session, entry.question_id, variant.id)

        response = self.client.get("/api/leaderboard/")

        self.assertEqual(response.status_code, 200)
        usernames = [row["username"] for row in response.data]
        self.assertIn("api-user", usernames)
        self.assertNotIn("viewer", usernames)
