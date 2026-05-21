from django.contrib import admin

from .models import (
    AnswerVariant,
    DailyActivity,
    ImportRun,
    LiveCodingAttempt,
    LiveCodingSession,
    LiveCodingSessionTask,
    LiveCodingTask,
    Question,
    Subject,
    TestAnswer,
    TestSession,
    TestSessionQuestion,
    Topic,
    UserLiveCodingProgress,
    UserQuestionProgress,
    UserSubjectStats,
)


class AnswerVariantInline(admin.TabularInline):
    model = AnswerVariant
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "topic", "short_text", "import_format", "source_file", "created_at")
    list_filter = ("subject", "topic", "import_format", "source_file")
    search_fields = ("text", "hash")
    inlines = [AnswerVariantInline]

    def short_text(self, obj):
        return obj.text[:120]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "imported_at", "created_at")
    search_fields = ("name", "slug")


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "title", "type", "order")
    list_filter = ("subject", "type")
    search_fields = ("title", "slug")


@admin.register(LiveCodingTask)
class LiveCodingTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "topic", "title", "language", "difficulty", "created_at")
    list_filter = ("subject", "topic", "language", "difficulty")
    search_fields = ("title", "prompt", "expected_solution", "hash")


@admin.register(UserQuestionProgress)
class UserQuestionProgressAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "question",
        "times_seen",
        "times_correct",
        "times_wrong",
        "current_streak",
        "is_mastered",
        "personal_weight",
    )
    list_filter = ("is_mastered", "question__subject")
    search_fields = ("user__username", "question__text")


admin.site.register(AnswerVariant)
admin.site.register(TestSession)
admin.site.register(TestSessionQuestion)
admin.site.register(TestAnswer)
admin.site.register(UserSubjectStats)
admin.site.register(UserLiveCodingProgress)
admin.site.register(LiveCodingSession)
admin.site.register(LiveCodingSessionTask)
admin.site.register(LiveCodingAttempt)
admin.site.register(DailyActivity)
admin.site.register(ImportRun)
