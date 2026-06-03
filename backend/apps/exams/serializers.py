import hashlib

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Count, Q, Sum
from rest_framework import serializers

from .models import (
    AnswerVariant,
    ImportRun,
    LiveCodingAttempt,
    LiveCodingSession,
    LiveCodingTask,
    Question,
    Subject,
    TestAnswer,
    TestSession,
    Topic,
    UserLiveCodingProgress,
    UserQuestionProgress,
    UserSubjectStats,
)
from .live_coding_services import get_next_live_coding_task
from .services import get_next_question


User = get_user_model()


def build_question_image_url(question, context):
    """Build an absolute URL the frontend can load directly in an `<img>` tag.

    Falls back to a root-relative path when no request is available in the serializer
    context (e.g. when serializing outside the request/response cycle).
    """
    image = getattr(question, "image", None)
    if not image:
        return None
    relative = f"/api/question-images/{str(image).lstrip('/')}"
    request = context.get("request") if context else None
    if request is not None:
        return request.build_absolute_uri(relative)
    return relative


def shuffled_answer_variants(question, session_id, question_order):
    variants = list(question.variants.all())
    original_ids = [variant.id for variant in variants]

    def sort_key(variant):
        payload = f"{session_id}:{question.id}:{question_order}:{variant.id}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    variants.sort(key=sort_key)

    # Avoid leaking the source/PDF order when the deterministic sort happens
    # to produce the same sequence.
    if len(variants) > 1 and [variant.id for variant in variants] == original_ids:
        payload = f"{session_id}:{question.id}:{question_order}:rotate".encode("utf-8")
        shift = int(hashlib.sha256(payload).hexdigest(), 16) % (len(variants) - 1) + 1
        variants = variants[shift:] + variants[:shift]

    return variants


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "password2")

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password2"):
            raise serializers.ValidationError({"password2": "Passwords do not match"})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )


class UserSerializer(serializers.ModelSerializer):
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "date_joined", "is_staff")


class TopicSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    live_coding_count = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Topic
        fields = (
            "id",
            "title",
            "slug",
            "type",
            "order",
            "question_count",
            "live_coding_count",
            "progress",
        )

    def get_question_count(self, obj):
        return getattr(obj, "question_count", None) or obj.questions.count()

    def get_live_coding_count(self, obj):
        return getattr(obj, "live_coding_count", None) or obj.live_coding_tasks.count()

    def get_progress(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        if obj.type == Topic.TYPE_LIVE_CODING:
            values = UserLiveCodingProgress.objects.filter(
                user=request.user,
                task__topic=obj,
            ).aggregate(
                total_answered=Sum("attempts_count"),
                solved=Count("id", filter=Q(is_solved=True)),
                unique_seen=Count("id"),
            )
            total = values["total_answered"] or 0
            solved = values["solved"] or 0
            return {
                "total_answered": total,
                "correct_answers": solved,
                "wrong_answers": max(total - solved, 0),
                "winrate": round(solved * 100 / total, 2) if total else 0,
                "unique_seen": values["unique_seen"] or 0,
            }

        values = UserQuestionProgress.objects.filter(
            user=request.user,
            question__topic=obj,
        ).aggregate(
            correct_answers=Sum("times_correct"),
            wrong_answers=Sum("times_wrong"),
            unique_seen=Count("id"),
        )
        correct = values["correct_answers"] or 0
        wrong = values["wrong_answers"] or 0
        total = correct + wrong
        return {
            "total_answered": total,
            "correct_answers": correct,
            "wrong_answers": wrong,
            "winrate": round(correct * 100 / total, 2) if total else 0,
            "unique_seen": values["unique_seen"] or 0,
        }


class TopicMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ("id", "title", "slug", "type")


class PublicAnswerVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerVariant
        fields = ("id", "text", "order")


class AnswerVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerVariant
        fields = ("id", "text", "is_correct", "order")


class QuestionForTestSerializer(serializers.ModelSerializer):
    variants = PublicAnswerVariantSerializer(many=True, read_only=True)
    topic = TopicMiniSerializer(read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ("id", "text", "topic", "difficulty", "variants", "image")

    def get_image(self, obj):
        return build_question_image_url(obj, self.context)


class QuestionReviewSerializer(QuestionForTestSerializer):
    """Question payload for review screens (mistakes), where revealing the
    explanation and formula is expected because the question was already answered."""

    class Meta(QuestionForTestSerializer.Meta):
        fields = QuestionForTestSerializer.Meta.fields + ("explanation", "formula")


class QuestionWithAnswersSerializer(serializers.ModelSerializer):
    variants = AnswerVariantSerializer(many=True, read_only=True)
    topic = TopicMiniSerializer(read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ("id", "text", "topic", "difficulty", "explanation", "formula", "variants", "source_file", "image")

    def get_image(self, obj):
        return build_question_image_url(obj, self.context)


class SubjectSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    live_coding_count = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    overall_completion_percent = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = (
            "id",
            "name",
            "slug",
            "imported_at",
            "question_count",
            "live_coding_count",
            "users_count",
            "overall_completion_percent",
        )

    def get_question_count(self, obj):
        return getattr(obj, "question_count", None) or obj.questions.count()

    def get_live_coding_count(self, obj):
        return getattr(obj, "live_coding_count", None) or obj.live_coding_tasks.count()

    def get_users_count(self, obj):
        annotated = getattr(obj, "users_count", None)
        if annotated is not None:
            return annotated
        return (
            UserQuestionProgress.objects.filter(question__subject=obj)
            .values("user_id")
            .distinct()
            .count()
        )

    def get_overall_completion_percent(self, obj):
        question_count = self.get_question_count(obj)
        users_count = self.get_users_count(obj)
        if not question_count or not users_count:
            return 0
        seen_records = getattr(obj, "seen_records_count", None)
        if seen_records is None:
            seen_records = UserQuestionProgress.objects.filter(question__subject=obj).count()
        return round(seen_records * 100 / (question_count * users_count), 2)


class SubjectDetailSerializer(SubjectSerializer):
    user_stats = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()

    class Meta(SubjectSerializer.Meta):
        fields = SubjectSerializer.Meta.fields + ("user_stats", "topics")

    def get_user_stats(self, obj):
        user = self.context["request"].user
        stats = UserSubjectStats.objects.filter(user=user, subject=obj).first()
        if not stats:
            return {
                "total_answered": 0,
                "unique_questions_seen": 0,
                "correct_answers": 0,
                "wrong_answers": 0,
                "live_coding_attempts": 0,
                "live_coding_solved": 0,
                "average_live_coding_similarity": 0,
                "winrate": 0,
                "points": 0,
                "last_activity_at": None,
            }
        return UserSubjectStatsSerializer(stats).data

    def get_topics(self, obj):
        topics = obj.topics.annotate(
            question_count=Count("questions", distinct=True),
            live_coding_count=Count("live_coding_tasks", distinct=True),
        ).order_by("type", "order", "title")
        return TopicSerializer(topics, many=True, context=self.context).data


class TestStartSerializer(serializers.Serializer):
    subject_id = serializers.IntegerField()
    mode = serializers.ChoiceField(choices=[choice[0] for choice in TestSession.MODE_CHOICES], default=TestSession.MODE_RANDOM)
    question_count = serializers.CharField(default="10")
    topic_id = serializers.IntegerField(required=False)
    topic_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )

    def validate_question_count(self, value):
        value = str(value).strip().lower()
        if value in {"5", "10", "20", "50", "all"}:
            return value
        try:
            count = int(value)
        except ValueError as exc:
            raise serializers.ValidationError("Use 5, 10, 20, 50, all, or a custom positive integer.") from exc
        if count < 1:
            raise serializers.ValidationError("Custom question count must be positive.")
        if count > 200:
            raise serializers.ValidationError("Custom question count cannot exceed 200.")
        return str(count)

    def validate(self, attrs):
        topic_ids = list(attrs.get("topic_ids") or [])
        topic_id = attrs.get("topic_id")
        if topic_id:
            topic_ids.append(topic_id)
        attrs["topic_ids"] = list(dict.fromkeys(topic_ids))
        return attrs


class TestAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_variant_id = serializers.IntegerField()
    time_spent = serializers.IntegerField(required=False, min_value=0, default=0)


class TestSessionStateSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    answered_count = serializers.SerializerMethodField()
    current_question = serializers.SerializerMethodField()

    class Meta:
        model = TestSession
        fields = (
            "id",
            "subject",
            "mode",
            "total_questions",
            "status",
            "started_at",
            "finished_at",
            "score",
            "correct_count",
            "wrong_count",
            "answered_count",
            "current_question",
        )

    def get_answered_count(self, obj):
        return obj.answers.count()

    def get_current_question(self, obj):
        entry = get_next_question(obj)
        if not entry:
            return None
        question = entry.question
        return {
            "order": entry.order,
            "question": {
                "id": question.id,
                "text": question.text,
                "topic": TopicMiniSerializer(question.topic).data if question.topic else None,
                "difficulty": question.difficulty,
                # Image is part of the prompt for visual questions, so it is safe to show
                # before answering. Explanation/formula are intentionally withheld here.
                "image": build_question_image_url(question, self.context),
                "variants": PublicAnswerVariantSerializer(
                    shuffled_answer_variants(question, obj.id, entry.order),
                    many=True,
                ).data,
            },
        }


class TestAnswerResultSerializer(serializers.ModelSerializer):
    correct_variant = serializers.SerializerMethodField()
    selected_variant = PublicAnswerVariantSerializer(read_only=True)
    question_stats = serializers.SerializerMethodField()
    explanation = serializers.SerializerMethodField()
    formula = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = TestAnswer
        fields = (
            "id",
            "question_id",
            "selected_variant",
            "is_correct",
            "points_awarded",
            "answered_at",
            "correct_variant",
            "question_stats",
            "explanation",
            "formula",
            "image",
        )

    def get_correct_variant(self, obj):
        variant = obj.question.variants.filter(is_correct=True).first()
        return AnswerVariantSerializer(variant).data if variant else None

    def get_explanation(self, obj):
        return obj.question.explanation or None

    def get_formula(self, obj):
        return obj.question.formula or None

    def get_image(self, obj):
        return build_question_image_url(obj.question, self.context)

    def get_question_stats(self, obj):
        progress = UserQuestionProgress.objects.filter(
            user=obj.session.user,
            question=obj.question,
        ).first()
        if not progress:
            return None
        return {
            "times_seen": progress.times_seen,
            "times_correct": progress.times_correct,
            "times_wrong": progress.times_wrong,
            "current_streak": progress.current_streak,
            "personal_winrate": progress.personal_winrate,
            "is_mastered": progress.is_mastered,
            "personal_weight": progress.personal_weight,
        }


class TestResultAnswerSerializer(serializers.ModelSerializer):
    question = QuestionWithAnswersSerializer(read_only=True)
    selected_variant = PublicAnswerVariantSerializer(read_only=True)

    class Meta:
        model = TestAnswer
        fields = (
            "id",
            "question",
            "selected_variant",
            "is_correct",
            "points_awarded",
            "time_spent",
            "answered_at",
        )


class TestResultSerializer(serializers.ModelSerializer):
    answers = TestResultAnswerSerializer(many=True, read_only=True)
    winrate = serializers.SerializerMethodField()

    class Meta:
        model = TestSession
        fields = (
            "id",
            "subject",
            "mode",
            "total_questions",
            "status",
            "started_at",
            "finished_at",
            "score",
            "correct_count",
            "wrong_count",
            "winrate",
            "answers",
        )

    def get_winrate(self, obj):
        total = obj.correct_count + obj.wrong_count
        return round(obj.correct_count * 100 / total, 2) if total else 0


class UserSubjectStatsSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_slug = serializers.CharField(source="subject.slug", read_only=True)
    winrate = serializers.FloatField(read_only=True)

    class Meta:
        model = UserSubjectStats
        fields = (
            "subject_id",
            "subject_name",
            "subject_slug",
            "total_answered",
            "unique_questions_seen",
            "correct_answers",
            "wrong_answers",
            "live_coding_attempts",
            "live_coding_solved",
            "average_live_coding_similarity",
            "winrate",
            "points",
            "last_activity_at",
        )


class MistakeSerializer(serializers.ModelSerializer):
    question = QuestionReviewSerializer(read_only=True)
    subject = serializers.CharField(source="question.subject.name", read_only=True)
    subject_id = serializers.IntegerField(source="question.subject_id", read_only=True)
    topic = TopicMiniSerializer(source="question.topic", read_only=True)
    personal_winrate = serializers.FloatField(read_only=True)

    class Meta:
        model = UserQuestionProgress
        fields = (
            "question",
            "subject",
            "subject_id",
            "topic",
            "times_seen",
            "times_correct",
            "times_wrong",
            "current_streak",
            "best_streak",
            "last_seen_at",
            "last_wrong_at",
            "is_mastered",
            "personal_winrate",
            "personal_weight",
        )


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    winrate = serializers.FloatField(read_only=True)
    rank = serializers.IntegerField(read_only=True)

    class Meta:
        model = UserSubjectStats
        fields = (
            "rank",
            "username",
            "points",
            "total_answered",
            "winrate",
            "unique_questions_seen",
            "live_coding_attempts",
            "live_coding_solved",
            "average_live_coding_similarity",
            "subject_id",
        )


class LiveCodingTaskSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="subject.name", read_only=True)
    subject_id = serializers.IntegerField(read_only=True)
    topic = TopicMiniSerializer(read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = LiveCodingTask
        fields = (
            "id",
            "subject",
            "subject_id",
            "topic",
            "title",
            "prompt",
            "language",
            "check_type",
            "difficulty",
            "tags",
            "progress",
        )

    def get_progress(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        progress = UserLiveCodingProgress.objects.filter(user=request.user, task=obj).first()
        if not progress:
            return {
                "attempts_count": 0,
                "best_similarity": 0,
                "last_similarity": 0,
                "is_solved": False,
                "points_earned": 0,
            }
        return {
            "attempts_count": progress.attempts_count,
            "best_similarity": progress.best_similarity,
            "last_similarity": progress.last_similarity,
            "is_solved": progress.is_solved,
            "points_earned": progress.points_earned,
        }


class LiveCodingStartSerializer(serializers.Serializer):
    subject_id = serializers.IntegerField()
    mode = serializers.ChoiceField(
        choices=[choice[0] for choice in LiveCodingSession.MODE_CHOICES],
        default=LiveCodingSession.MODE_RANDOM,
    )
    task_count = serializers.CharField(default="10")
    topic_id = serializers.IntegerField(required=False)
    topic_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )

    def validate_task_count(self, value):
        value = str(value).strip().lower()
        if value in {"5", "10", "20", "50", "all"}:
            return value
        try:
            count = int(value)
        except ValueError as exc:
            raise serializers.ValidationError("Use 5, 10, 20, 50, all, or a custom positive integer.") from exc
        if count < 1:
            raise serializers.ValidationError("Custom task count must be positive.")
        if count > 200:
            raise serializers.ValidationError("Custom task count cannot exceed 200.")
        return str(count)

    def validate(self, attrs):
        topic_ids = list(attrs.get("topic_ids") or [])
        topic_id = attrs.get("topic_id")
        if topic_id:
            topic_ids.append(topic_id)
        attrs["topic_ids"] = list(dict.fromkeys(topic_ids))
        return attrs


class LiveCodingSubmitSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    submitted_code = serializers.CharField(allow_blank=True, trim_whitespace=False)
    time_spent = serializers.IntegerField(required=False, min_value=0, default=0)


class LiveCodingSessionStateSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    answered_count = serializers.SerializerMethodField()
    current_task = serializers.SerializerMethodField()

    class Meta:
        model = LiveCodingSession
        fields = (
            "id",
            "subject",
            "mode",
            "total_tasks",
            "status",
            "started_at",
            "finished_at",
            "score",
            "average_similarity",
            "answered_count",
            "current_task",
        )

    def get_answered_count(self, obj):
        return obj.attempts.values("task_id").distinct().count()

    def get_current_task(self, obj):
        entry = get_next_live_coding_task(obj)
        if not entry:
            return None
        return {
            "order": entry.order,
            "task": LiveCodingTaskSerializer(entry.task, context=self.context).data,
        }


class LiveCodingAttemptSerializer(serializers.ModelSerializer):
    task = LiveCodingTaskSerializer(read_only=True)
    expected_solution = serializers.CharField(source="task.expected_solution", read_only=True)

    class Meta:
        model = LiveCodingAttempt
        fields = (
            "id",
            "task",
            "similarity_score",
            "status",
            "points_awarded",
            "feedback",
            "expected_solution",
            "submitted_code",
            "attempted_at",
            "time_spent",
        )


class LiveCodingResultSerializer(serializers.ModelSerializer):
    subject = SubjectSerializer(read_only=True)
    attempts = LiveCodingAttemptSerializer(many=True, read_only=True)

    class Meta:
        model = LiveCodingSession
        fields = (
            "id",
            "subject",
            "mode",
            "total_tasks",
            "status",
            "started_at",
            "finished_at",
            "score",
            "average_similarity",
            "attempts",
        )


class LiveCodingWeakTaskSerializer(serializers.ModelSerializer):
    task = LiveCodingTaskSerializer(read_only=True)
    subject = serializers.CharField(source="task.subject.name", read_only=True)
    subject_id = serializers.IntegerField(source="task.subject_id", read_only=True)
    topic = TopicMiniSerializer(source="task.topic", read_only=True)

    class Meta:
        model = UserLiveCodingProgress
        fields = (
            "task",
            "subject",
            "subject_id",
            "topic",
            "attempts_count",
            "best_similarity",
            "last_similarity",
            "is_solved",
            "last_attempt_at",
            "points_earned",
        )


class ImportRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRun
        fields = (
            "id",
            "status",
            "base_dir",
            "started_at",
            "finished_at",
            "subjects_found",
            "files_found",
            "imported_questions",
            "duplicate_questions",
            "skipped_questions",
            "imported_live_coding_tasks",
            "duplicate_live_coding_tasks",
            "skipped_live_coding_tasks",
            "errors",
        )
