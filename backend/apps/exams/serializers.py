import hashlib

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import (
    AnswerVariant,
    ImportRun,
    Question,
    Subject,
    TestAnswer,
    TestSession,
    UserQuestionProgress,
    UserSubjectStats,
)
from .services import get_next_question


User = get_user_model()


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

    class Meta:
        model = Question
        fields = ("id", "text", "variants")


class QuestionWithAnswersSerializer(serializers.ModelSerializer):
    variants = AnswerVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ("id", "text", "variants", "source_file")


class SubjectSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
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
            "users_count",
            "overall_completion_percent",
        )

    def get_question_count(self, obj):
        return getattr(obj, "question_count", None) or obj.questions.count()

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

    class Meta(SubjectSerializer.Meta):
        fields = SubjectSerializer.Meta.fields + ("user_stats",)

    def get_user_stats(self, obj):
        user = self.context["request"].user
        stats = UserSubjectStats.objects.filter(user=user, subject=obj).first()
        if not stats:
            return {
                "total_answered": 0,
                "unique_questions_seen": 0,
                "correct_answers": 0,
                "wrong_answers": 0,
                "winrate": 0,
                "points": 0,
                "last_activity_at": None,
            }
        return UserSubjectStatsSerializer(stats).data


class TestStartSerializer(serializers.Serializer):
    subject_id = serializers.IntegerField()
    mode = serializers.ChoiceField(choices=[choice[0] for choice in TestSession.MODE_CHOICES], default=TestSession.MODE_RANDOM)
    question_count = serializers.CharField(default="10")

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
        )

    def get_correct_variant(self, obj):
        variant = obj.question.variants.filter(is_correct=True).first()
        return AnswerVariantSerializer(variant).data if variant else None

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
            "winrate",
            "points",
            "last_activity_at",
        )


class MistakeSerializer(serializers.ModelSerializer):
    question = QuestionForTestSerializer(read_only=True)
    subject = serializers.CharField(source="question.subject.name", read_only=True)
    subject_id = serializers.IntegerField(source="question.subject_id", read_only=True)
    personal_winrate = serializers.FloatField(read_only=True)

    class Meta:
        model = UserQuestionProgress
        fields = (
            "question",
            "subject",
            "subject_id",
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
            "subject_id",
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
            "errors",
        )
