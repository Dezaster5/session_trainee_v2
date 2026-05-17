from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    HealthView,
    ImportQuestionsView,
    ImportStatusView,
    LeaderboardView,
    LoginView,
    LogoutView,
    MarkQuestionMasteredView,
    MeView,
    MistakesView,
    ProgressSubjectsView,
    ProgressSummaryView,
    RegisterView,
    SubjectDetailView,
    SubjectListView,
    TestAnswerView,
    TestFinishView,
    TestResultView,
    TestSessionDetailView,
    TestStartView,
)


urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("subjects/", SubjectListView.as_view(), name="subjects"),
    path("subjects/<int:pk>/", SubjectDetailView.as_view(), name="subject-detail"),
    path("tests/start/", TestStartView.as_view(), name="test-start"),
    path("tests/<int:pk>/", TestSessionDetailView.as_view(), name="test-detail"),
    path("tests/<int:pk>/answer/", TestAnswerView.as_view(), name="test-answer"),
    path("tests/<int:pk>/finish/", TestFinishView.as_view(), name="test-finish"),
    path("tests/<int:pk>/result/", TestResultView.as_view(), name="test-result"),
    path("progress/summary/", ProgressSummaryView.as_view(), name="progress-summary"),
    path("progress/subjects/", ProgressSubjectsView.as_view(), name="progress-subjects"),
    path("progress/mistakes/", MistakesView.as_view(), name="progress-mistakes"),
    path("progress/questions/<int:question_id>/mark-mastered/", MarkQuestionMasteredView.as_view(), name="mark-mastered"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("admin/import-questions/", ImportQuestionsView.as_view(), name="admin-import-questions"),
    path("admin/import-status/", ImportStatusView.as_view(), name="admin-import-status"),
]
