import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .importer import import_questions_from_base, parse_json_live_coding, parse_tagged_questions, question_hash, validate_question
from .live_coding_services import (
    calculate_final_similarity,
    create_live_coding_session,
    submit_live_coding_attempt,
)
from .models import (
    AnswerVariant,
    LiveCodingTask,
    Question,
    Subject,
    TestSession,
    TestSessionQuestion,
    Topic,
    UserLiveCodingProgress,
    UserQuestionProgress,
    UserSubjectStats,
)
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


class JsonImportTests(TestCase):
    def test_web_component_json_has_no_live_coding_placeholder_solutions(self):
        path = settings.BASE_QUESTIONS_DIR / "Web_component_development" / "final_exam_questions.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        placeholder_markers = (
            "Implement the requested logic here",
            "Provide a complete Spring Boot code snippet",
            "where appropriate",
            "public class Solution",
            "your code",
        )
        placeholders = [
            item["id"]
            for item in data.get("liveCoding", [])
            if any(marker in item.get("expected_solution", "") for marker in placeholder_markers)
        ]
        comment_only = []
        for item in data.get("liveCoding", []):
            solution_lines = [
                line.strip()
                for line in item.get("expected_solution", "").splitlines()
                if line.strip()
            ]
            if solution_lines and all(line.startswith(("//", "#")) for line in solution_lines):
                comment_only.append(item["id"])

        password_task = next(item for item in data["liveCoding"] if item["id"] == "LC0233")
        rectangle_task = next(item for item in data["liveCoding"] if item["id"] == "LC0136")
        read_file_task = next(item for item in data["liveCoding"] if item["id"] == "LC0186")

        self.assertEqual(placeholders, [])
        self.assertEqual(comment_only, [])
        self.assertIn("PasswordEncoder", password_task["expected_solution"])
        self.assertIn("passwordEncoder.encode", password_task["expected_solution"])
        self.assertIn("@GetMapping(\"/rectangle/perimeter\")", rectangle_task["expected_solution"])
        self.assertIn("return 2 * (length + width)", rectangle_task["expected_solution"])
        self.assertIn("Files.readString", read_file_task["expected_solution"])
        self.assertIn("catch (IOException", read_file_task["expected_solution"])

    def test_json_live_coding_parser_preserves_solution_formatting(self):
        parsed = parse_json_live_coding(
            {
                "liveCoding": [
                    {
                        "id": "LCX",
                        "topic": "Java",
                        "task": "Write formatted code.",
                        "expected_solution_language": "java",
                        "expected_solution": """public class Demo {
    void run() {
        System.out.println("ok");
    }
}""",
                    }
                ]
            }
        )

        self.assertIn("\n    void run()", parsed[0]["expected_solution"])
        self.assertIn("\n        System.out.println", parsed[0]["expected_solution"])

    def test_imports_json_questions_topics_and_live_coding_without_duplicates(self):
        payload = {
            "questions": [
                {
                    "id": "Q1",
                    "topic": "Spring Boot / Backend",
                    "subtopic": "Spring Fundamentals",
                    "question": "What does @RestController do?",
                    "options": [
                        {"id": "A", "text": "Marks a REST controller", "is_correct": True},
                        {"id": "B", "text": "Creates a database", "is_correct": False},
                    ],
                    "correct_option_id": "A",
                    "explanation": "It combines controller and response body behavior.",
                }
            ],
            "liveCoding": [
                {
                    "id": "LC1",
                    "topic": "Docker",
                    "task": "Write the command to check Docker version.",
                    "expected_solution_language": "shell",
                    "expected_solution": "docker --version",
                    "checking_method": {"mode": "similarity_percentage"},
                }
            ],
        }

        with TemporaryDirectory() as tmp:
            subject_dir = Path(tmp) / "Web_component_development"
            subject_dir.mkdir()
            (subject_dir / "final_exam_questions.json").write_text(json.dumps(payload), encoding="utf-8")

            first = import_questions_from_base(tmp)
            second = import_questions_from_base(tmp)

        subject = Subject.objects.get(slug="web_component_development")
        question = Question.objects.get(subject=subject)
        task = LiveCodingTask.objects.get(subject=subject)

        self.assertEqual(subject.name, "Web Component Development")
        self.assertEqual(Topic.objects.filter(subject=subject, type=Topic.TYPE_THEORY).count(), 1)
        self.assertEqual(Topic.objects.filter(subject=subject, type=Topic.TYPE_LIVE_CODING).count(), 1)
        self.assertEqual(question.import_format, Question.FORMAT_JSON)
        self.assertEqual(question.variants.count(), 2)
        self.assertEqual(question.variants.get(is_correct=True).text, "Marks a REST controller")
        self.assertEqual(task.expected_solution, "docker --version")
        self.assertEqual(first.imported_questions, 1)
        self.assertEqual(first.imported_live_coding_tasks, 1)
        self.assertEqual(second.imported_questions, 0)
        self.assertEqual(second.imported_live_coding_tasks, 0)
        self.assertEqual(Question.objects.count(), 1)
        self.assertEqual(LiveCodingTask.objects.count(), 1)


class TestSelectionAndScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="strong-pass-123")
        self.subject = Subject.objects.create(name="Machine Learning", slug="machine-learning")
        self.topic_a = Topic.objects.create(subject=self.subject, title="Topic A", slug="topic-a", type=Topic.TYPE_THEORY, order=1)
        self.topic_b = Topic.objects.create(subject=self.subject, title="Topic B", slug="topic-b", type=Topic.TYPE_THEORY, order=2)
        self.questions = []
        for index in range(6):
            question = Question.objects.create(
                subject=self.subject,
                topic=self.topic_a if index < 3 else self.topic_b,
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

    def test_question_selection_filters_by_topic_ids(self):
        selected = select_questions(
            self.user,
            self.subject,
            TestSession.MODE_REVIEW_ALL,
            10,
            topic_ids=[self.topic_a.id],
        )
        session = create_test_session(
            self.user,
            self.subject,
            TestSession.MODE_REVIEW_ALL,
            10,
            topic_ids=[self.topic_a.id],
        )

        self.assertEqual(len(selected), 3)
        self.assertTrue(all(question.topic_id == self.topic_a.id for question in selected))
        self.assertEqual(session.session_questions.count(), 3)
        self.assertTrue(all(item.question.topic_id == self.topic_a.id for item in session.session_questions.select_related("question")))

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


class LiveCodingServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="coder", password="strong-pass-123")
        self.subject = Subject.objects.create(name="Web Component Development", slug="web_component_development")
        self.topic = Topic.objects.create(
            subject=self.subject,
            title="Docker",
            slug="docker",
            type=Topic.TYPE_LIVE_CODING,
            order=1,
        )
        self.task = LiveCodingTask.objects.create(
            subject=self.subject,
            topic=self.topic,
            title="Docker version",
            prompt="Write the command to check Docker version.",
            language="shell",
            expected_solution="docker --version",
            source_file="sample.json",
            hash="live-hash-1",
        )

    def test_similarity_accepts_exact_and_near_command_answers(self):
        exact = calculate_final_similarity("docker --version", "docker --version", "shell", "similarity")
        near = calculate_final_similarity("docker version", "docker --version", "shell", "similarity")

        self.assertEqual(exact, 100)
        self.assertGreaterEqual(near, 70)

    def test_similarity_ignores_java_formatting(self):
        expected = "@RestController public class HelloController { @GetMapping(\"/hi\") public String hi(){ return \"hi\"; } }"
        submitted = """
        @RestController
        public class HelloController {
          @GetMapping("/hi")
          public String hi() {
            return "hi";
          }
        }
        """

        score = calculate_final_similarity(submitted, expected, "java", "similarity")

        self.assertGreaterEqual(score, 90)

    def test_submit_attempt_updates_progress_stats_and_caps_points(self):
        session = create_live_coding_session(
            self.user,
            self.subject,
            "review_all",
            1,
            topic_ids=[self.topic.id],
        )

        attempt, progress = submit_live_coding_attempt(session, self.task.id, "docker --version")
        stats = UserSubjectStats.objects.get(user=self.user, subject=self.subject)

        self.assertEqual(attempt.status, "excellent")
        self.assertTrue(progress.is_solved)
        self.assertEqual(progress.attempts_count, 1)
        self.assertEqual(stats.live_coding_attempts, 1)
        self.assertEqual(stats.live_coding_solved, 1)
        self.assertEqual(attempt.points_awarded, 15)

        repeat_session = create_live_coding_session(
            self.user,
            self.subject,
            "review_all",
            1,
            topic_ids=[self.topic.id],
        )
        repeat_attempt, repeat_progress = submit_live_coding_attempt(repeat_session, self.task.id, "docker --version")
        repeat_session_2 = create_live_coding_session(
            self.user,
            self.subject,
            "review_all",
            1,
            topic_ids=[self.topic.id],
        )
        third_attempt, repeat_progress = submit_live_coding_attempt(repeat_session_2, self.task.id, "docker --version")

        self.assertEqual(repeat_attempt.points_awarded, 5)
        self.assertEqual(third_attempt.points_awarded, 0)
        self.assertEqual(repeat_progress.points_earned, 20)

    def test_duplicate_attempt_in_same_session_is_rejected(self):
        LiveCodingTask.objects.create(
            subject=self.subject,
            topic=self.topic,
            title="Docker ps",
            prompt="Write the command to list running containers.",
            language="shell",
            expected_solution="docker ps",
            source_file="sample.json",
            hash="live-hash-2",
        )
        session = create_live_coding_session(
            self.user,
            self.subject,
            "review_all",
            2,
            topic_ids=[self.topic.id],
        )
        task_id = session.session_tasks.first().task_id
        submit_live_coding_attempt(session, task_id, "docker --version")

        with self.assertRaisesMessage(ValueError, "already been attempted"):
            submit_live_coding_attempt(session, task_id, "docker --version")

        self.assertEqual(session.attempts.count(), 1)


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

    def test_start_test_without_topic_ids_keeps_existing_flow(self):
        response = self.client.post(
            "/api/tests/start/",
            {"subject_id": self.subject.id, "mode": "random", "question_count": "10"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["total_questions"], 1)
        self.assertIsNotNone(response.data["current_question"])

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

    def test_leaderboard_handles_live_coding_aggregates(self):
        coder = User.objects.create_user(username="coder", password="strong-pass-123")
        second_subject = Subject.objects.create(name="Web", slug="web")
        UserSubjectStats.objects.create(
            user=coder,
            subject=self.subject,
            live_coding_attempts=2,
            live_coding_solved=1,
            average_live_coding_similarity=80,
            points=20,
        )
        UserSubjectStats.objects.create(
            user=coder,
            subject=second_subject,
            live_coding_attempts=3,
            live_coding_solved=2,
            average_live_coding_similarity=90,
            points=30,
        )

        response = self.client.get("/api/leaderboard/")
        live_response = self.client.get("/api/leaderboard/?type=live_coding")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(live_response.status_code, 200)
        row = next(item for item in live_response.data if item["username"] == "coder")
        self.assertEqual(row["live_coding_attempts"], 5)
        self.assertEqual(row["live_coding_solved"], 3)
        self.assertEqual(row["average_live_coding_similarity"], 86)

    def test_subject_topics_endpoint_returns_counts(self):
        topic = Topic.objects.create(subject=self.subject, title="Theory Topic", slug="theory-topic", type=Topic.TYPE_THEORY)
        self.question.topic = topic
        self.question.save(update_fields=["topic"])

        response = self.client.get(f"/api/subjects/{self.subject.id}/topics/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["question_count"], 1)
        self.assertEqual(response.data[0]["progress"]["unique_seen"], 0)

    def test_start_test_accepts_topic_ids(self):
        topic = Topic.objects.create(subject=self.subject, title="Theory Topic", slug="theory-topic", type=Topic.TYPE_THEORY)
        self.question.topic = topic
        self.question.save(update_fields=["topic"])

        response = self.client.post(
            "/api/tests/start/",
            {
                "subject_id": self.subject.id,
                "mode": "review_all",
                "question_count": "10",
                "topic_ids": [topic.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["total_questions"], 1)

    def test_start_test_with_empty_topic_pool_returns_clear_error(self):
        topic = Topic.objects.create(subject=self.subject, title="Empty Topic", slug="empty-topic", type=Topic.TYPE_THEORY)

        response = self.client.post(
            "/api/tests/start/",
            {
                "subject_id": self.subject.id,
                "mode": "review_all",
                "question_count": "10",
                "topic_ids": [topic.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("No questions available", response.data["detail"])

    def test_live_coding_api_start_submit_and_mistakes(self):
        topic = Topic.objects.create(
            subject=self.subject,
            title="Docker",
            slug="docker",
            type=Topic.TYPE_LIVE_CODING,
        )
        task = LiveCodingTask.objects.create(
            subject=self.subject,
            topic=topic,
            title="Docker version",
            prompt="Write Docker version command.",
            language="shell",
            expected_solution="docker --version",
            source_file="sample.json",
            hash="api-live-hash",
        )
        LiveCodingTask.objects.create(
            subject=self.subject,
            topic=topic,
            title="Docker ps",
            prompt="Write Docker ps command.",
            language="shell",
            expected_solution="docker ps",
            source_file="sample.json",
            hash="api-live-hash-2",
        )

        start = self.client.post(
            "/api/live-coding/start/",
            {
                "subject_id": self.subject.id,
                "mode": "review_all",
                "task_count": "2",
                "topic_ids": [topic.id],
            },
            format="json",
        )
        self.assertEqual(start.status_code, 201)
        current_task_id = start.data["current_task"]["task"]["id"]
        expected_solution = LiveCodingTask.objects.get(pk=current_task_id).expected_solution

        submit = self.client.post(
            f"/api/live-coding/{start.data['id']}/submit/",
            {"task_id": current_task_id, "submitted_code": expected_solution, "time_spent": 3},
            format="json",
        )
        self.assertEqual(submit.status_code, 200)
        self.assertIn("expected_solution", submit.data["attempt"])

        duplicate = self.client.post(
            f"/api/live-coding/{start.data['id']}/submit/",
            {"task_id": current_task_id, "submitted_code": expected_solution},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("already been attempted", duplicate.data["detail"])

        result = self.client.get(f"/api/live-coding/{start.data['id']}/result/")
        mistakes = self.client.get("/api/progress/live-coding/mistakes/")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["attempts"][0]["similarity_score"], 100)
        self.assertEqual(mistakes.status_code, 200)

    def test_live_coding_mistakes_returns_weak_tasks(self):
        topic = Topic.objects.create(
            subject=self.subject,
            title="Docker",
            slug="docker-weak",
            type=Topic.TYPE_LIVE_CODING,
        )
        task = LiveCodingTask.objects.create(
            subject=self.subject,
            topic=topic,
            title="Docker ps",
            prompt="List containers.",
            language="shell",
            expected_solution="docker ps",
            source_file="sample.json",
            hash="api-live-weak-hash",
        )
        session = create_live_coding_session(self.user, self.subject, "review_all", 1, topic_ids=[topic.id])
        submit_live_coding_attempt(session, task.id, "git status")

        response = self.client.get("/api/progress/live-coding/mistakes/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["task"]["id"], task.id)
