from django.contrib import admin

from .models import (
    AnswerVariant,
    DailyActivity,
    ImportRun,
    Question,
    Subject,
    TestAnswer,
    TestSession,
    TestSessionQuestion,
    UserQuestionProgress,
    UserSubjectStats,
)


class AnswerVariantInline(admin.TabularInline):
    model = AnswerVariant
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "short_text", "source_file", "created_at")
    list_filter = ("subject", "source_file")
    search_fields = ("text", "hash")
    inlines = [AnswerVariantInline]

    def short_text(self, obj):
        return obj.text[:120]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "imported_at", "created_at")
    search_fields = ("name", "slug")


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
admin.site.register(DailyActivity)
admin.site.register(ImportRun)
