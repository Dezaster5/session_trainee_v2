from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Subject(models.Model):
    name = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True)
    source_path = models.CharField(max_length=500, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Question(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    source_file = models.CharField(max_length=500)
    hash = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["subject", "hash"]),
            models.Index(fields=["subject", "created_at"]),
        ]

    def __str__(self):
        return self.text[:100]


class AnswerVariant(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="variants")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "text"],
                name="unique_variant_text_per_question",
            ),
            models.UniqueConstraint(
                fields=["question"],
                condition=Q(is_correct=True),
                name="unique_correct_variant_per_question",
            ),
        ]

    def __str__(self):
        return self.text[:100]


class UserQuestionProgress(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="question_progress",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="progress_records",
    )
    times_seen = models.PositiveIntegerField(default=0)
    times_correct = models.PositiveIntegerField(default=0)
    times_wrong = models.PositiveIntegerField(default=0)
    current_streak = models.IntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_correct_at = models.DateTimeField(null=True, blank=True)
    last_wrong_at = models.DateTimeField(null=True, blank=True)
    is_mastered = models.BooleanField(default=False)
    personal_weight = models.FloatField(default=1.0)
    points_earned = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "question"], name="unique_user_question_progress")
        ]
        indexes = [
            models.Index(fields=["user", "question"]),
            models.Index(fields=["user", "is_mastered"]),
            models.Index(fields=["user", "times_wrong"]),
        ]

    @property
    def personal_winrate(self):
        total = self.times_correct + self.times_wrong
        if total == 0:
            return None
        return round(self.times_correct * 100 / total, 2)

    def __str__(self):
        return f"{self.user_id}:{self.question_id}"


class TestSession(models.Model):
    MODE_RANDOM = "random"
    MODE_NEW = "new"
    MODE_MISTAKES = "mistakes"
    MODE_HARD = "hard"
    MODE_RARE = "rare"
    MODE_REVIEW_ALL = "review_all"
    MODE_SPACED = "spaced"

    MODE_CHOICES = [
        (MODE_RANDOM, "Random weighted"),
        (MODE_NEW, "Only new questions"),
        (MODE_MISTAKES, "Work on mistakes"),
        (MODE_HARD, "Hard questions"),
        (MODE_RARE, "Rarely seen questions"),
        (MODE_REVIEW_ALL, "Review all"),
        (MODE_SPACED, "Spaced repetition"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_FINISHED = "finished"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_FINISHED, "Finished"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="test_sessions")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="test_sessions")
    mode = models.CharField(max_length=32, choices=MODE_CHOICES, default=MODE_RANDOM)
    total_questions = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.IntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["subject", "started_at"]),
        ]

    def finish(self):
        self.status = self.STATUS_FINISHED
        self.finished_at = self.finished_at or timezone.now()
        self.save(update_fields=["status", "finished_at"])

    def __str__(self):
        return f"Session {self.pk} {self.user_id} {self.subject_id}"


class TestSessionQuestion(models.Model):
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name="session_questions")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="session_entries")
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["session", "question"], name="unique_question_per_session"),
            models.UniqueConstraint(fields=["session", "order"], name="unique_order_per_session"),
        ]

    def __str__(self):
        return f"{self.session_id}:{self.order}"


class TestAnswer(models.Model):
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="test_answers")
    selected_variant = models.ForeignKey(
        AnswerVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="selected_answers",
    )
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now_add=True)
    time_spent = models.PositiveIntegerField(default=0)
    points_awarded = models.IntegerField(default=0)

    class Meta:
        ordering = ["answered_at"]
        constraints = [
            models.UniqueConstraint(fields=["session", "question"], name="unique_answer_per_question_session")
        ]
        indexes = [
            models.Index(fields=["session", "question"]),
            models.Index(fields=["question", "is_correct"]),
        ]

    def __str__(self):
        return f"{self.session_id}:{self.question_id}:{self.is_correct}"


class UserSubjectStats(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subject_stats",
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="user_stats")
    total_answered = models.PositiveIntegerField(default=0)
    unique_questions_seen = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    wrong_answers = models.PositiveIntegerField(default=0)
    points = models.IntegerField(default=0)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "subject"], name="unique_user_subject_stats")
        ]
        indexes = [
            models.Index(fields=["user", "subject"]),
            models.Index(fields=["subject", "-points"]),
        ]

    @property
    def winrate(self):
        if self.total_answered == 0:
            return 0
        return round(self.correct_answers * 100 / self.total_answered, 2)

    def __str__(self):
        return f"{self.user_id}:{self.subject_id}"


class DailyActivity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_activity")
    day = models.DateField()
    total_answers = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    wrong_answers = models.PositiveIntegerField(default=0)
    points = models.IntegerField(default=0)

    class Meta:
        ordering = ["day"]
        constraints = [
            models.UniqueConstraint(fields=["user", "day"], name="unique_daily_activity")
        ]
        indexes = [models.Index(fields=["user", "day"])]

    def __str__(self):
        return f"{self.user_id}:{self.day}"


class ImportRun(models.Model):
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    base_dir = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    subjects_found = models.PositiveIntegerField(default=0)
    files_found = models.PositiveIntegerField(default=0)
    imported_questions = models.PositiveIntegerField(default=0)
    duplicate_questions = models.PositiveIntegerField(default=0)
    skipped_questions = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def complete(self, status):
        self.status = status
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "finished_at"])

    def __str__(self):
        return f"ImportRun {self.pk} {self.status}"
