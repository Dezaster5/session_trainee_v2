from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .importer import import_questions_from_base
from .models import DailyActivity, ImportRun, Subject, TestSession, UserQuestionProgress, UserSubjectStats
from .serializers import (
    ImportRunSerializer,
    LeaderboardEntrySerializer,
    MistakeSerializer,
    RegisterSerializer,
    SubjectDetailSerializer,
    SubjectSerializer,
    TestAnswerInputSerializer,
    TestAnswerResultSerializer,
    TestResultSerializer,
    TestSessionStateSerializer,
    TestStartSerializer,
    UserSerializer,
)
from .services import (
    aggregate_user_totals,
    create_test_session,
    get_next_question,
    leaderboard_queryset,
    record_answer,
    subject_progress_rows,
)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]


class LogoutView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except Exception:
                pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class SubjectListView(generics.ListAPIView):
    serializer_class = SubjectSerializer

    def get_queryset(self):
        return Subject.objects.annotate(
            question_count=Count("questions", distinct=True),
            users_count=Count("questions__progress_records__user", distinct=True),
            seen_records_count=Count("questions__progress_records", distinct=True),
        ).order_by("name")


class SubjectDetailView(generics.RetrieveAPIView):
    serializer_class = SubjectDetailSerializer
    queryset = Subject.objects.annotate(
        question_count=Count("questions", distinct=True),
        users_count=Count("questions__progress_records__user", distinct=True),
        seen_records_count=Count("questions__progress_records", distinct=True),
    )


class TestStartView(APIView):
    def post(self, request):
        serializer = TestStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject = get_object_or_404(Subject, pk=serializer.validated_data["subject_id"])
        session = create_test_session(
            user=request.user,
            subject=subject,
            mode=serializer.validated_data["mode"],
            requested_count=serializer.validated_data["question_count"],
        )
        if session is None:
            return Response(
                {"detail": "No questions available for the selected mode."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(TestSessionStateSerializer(session, context={"request": request}).data, status=status.HTTP_201_CREATED)


class TestSessionDetailView(generics.RetrieveAPIView):
    serializer_class = TestSessionStateSerializer

    def get_queryset(self):
        return TestSession.objects.filter(user=self.request.user).select_related("subject")


class TestAnswerView(APIView):
    def post(self, request, pk):
        session = get_object_or_404(TestSession.objects.select_related("subject", "user"), pk=pk, user=request.user)
        serializer = TestAnswerInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            answer, _progress = record_answer(
                session=session,
                question_id=serializer.validated_data["question_id"],
                selected_variant_id=serializer.validated_data["selected_variant_id"],
                time_spent=serializer.validated_data.get("time_spent", 0),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        answer = answer.__class__.objects.select_related("question", "selected_variant", "session").get(pk=answer.pk)
        session.refresh_from_db()
        return Response(
            {
                "answer": TestAnswerResultSerializer(answer, context={"request": request}).data,
                "session": TestSessionStateSerializer(session, context={"request": request}).data,
                "has_next": get_next_question(session) is not None,
            }
        )


class TestFinishView(APIView):
    def post(self, request, pk):
        session = get_object_or_404(TestSession, pk=pk, user=request.user)
        session.finish()
        return Response(TestSessionStateSerializer(session, context={"request": request}).data)


class TestResultView(generics.RetrieveAPIView):
    serializer_class = TestResultSerializer

    def get_queryset(self):
        return (
            TestSession.objects.filter(user=self.request.user)
            .select_related("subject")
            .prefetch_related("answers__question__variants", "answers__selected_variant")
        )


class ProgressSummaryView(APIView):
    def get(self, request):
        totals = aggregate_user_totals(request.user)
        subject_rows = subject_progress_rows(request.user)
        last_session = TestSession.objects.filter(user=request.user).select_related("subject").first()
        recent_sessions = TestSession.objects.filter(user=request.user).select_related("subject")[:5]

        top_hard = (
            UserQuestionProgress.objects.filter(user=request.user, times_wrong__gt=0)
            .select_related("question", "question__subject")
            .order_by("-personal_weight", "-times_wrong", "times_correct")[:6]
        )
        due_questions = (
            UserQuestionProgress.objects.filter(user=request.user)
            .filter(Q(times_wrong__gt=0) | Q(personal_weight__gte=1.5))
            .select_related("question", "question__subject")
            .order_by("-personal_weight", "last_seen_at")[:6]
        )
        activity_since = timezone.now().date() - timedelta(days=29)
        activity = DailyActivity.objects.filter(user=request.user, day__gte=activity_since).order_by("day")

        return Response(
            {
                "user": UserSerializer(request.user).data,
                "totals": totals,
                "subjects": subject_rows,
                "last_subject": SubjectSerializer(last_session.subject).data if last_session else None,
                "top_hard_questions": MistakeSerializer(top_hard, many=True).data,
                "today_better_repeat": MistakeSerializer(due_questions, many=True).data,
                "activity": [
                    {
                        "day": item.day,
                        "total_answers": item.total_answers,
                        "correct_answers": item.correct_answers,
                        "wrong_answers": item.wrong_answers,
                        "points": item.points,
                    }
                    for item in activity
                ],
                "recent_sessions": [
                    {
                        "id": session.id,
                        "subject": session.subject.name,
                        "mode": session.mode,
                        "status": session.status,
                        "score": session.score,
                        "correct_count": session.correct_count,
                        "wrong_count": session.wrong_count,
                        "total_questions": session.total_questions,
                        "started_at": session.started_at,
                        "finished_at": session.finished_at,
                    }
                    for session in recent_sessions
                ],
            }
        )


class ProgressSubjectsView(APIView):
    def get(self, request):
        return Response(subject_progress_rows(request.user))


class MistakesView(generics.ListAPIView):
    serializer_class = MistakeSerializer

    def get_queryset(self):
        queryset = (
            UserQuestionProgress.objects.filter(user=self.request.user, times_wrong__gt=0)
            .select_related("question", "question__subject")
            .prefetch_related("question__variants")
        )
        subject_id = self.request.query_params.get("subject")
        min_wrong = self.request.query_params.get("min_wrong")
        low_winrate = self.request.query_params.get("low_winrate")

        if subject_id:
            queryset = queryset.filter(question__subject_id=subject_id)
        if min_wrong:
            try:
                queryset = queryset.filter(times_wrong__gte=int(min_wrong))
            except ValueError as exc:
                raise ValidationError({"min_wrong": "Must be an integer."}) from exc
        if str(low_winrate).lower() in {"1", "true", "yes"}:
            queryset = queryset.filter(times_correct__lt=F("times_wrong"))

        ordering = self.request.query_params.get("ordering", "-last_wrong_at")
        allowed = {
            "-last_wrong_at",
            "last_wrong_at",
            "-times_wrong",
            "times_wrong",
            "-personal_weight",
            "personal_weight",
        }
        if ordering not in allowed:
            ordering = "-last_wrong_at"
        return queryset.order_by(ordering)


class MarkQuestionMasteredView(APIView):
    def post(self, request, question_id):
        progress = get_object_or_404(UserQuestionProgress, user=request.user, question_id=question_id)
        progress.is_mastered = True
        progress.personal_weight = min(progress.personal_weight, 0.35)
        progress.save(update_fields=["is_mastered", "personal_weight", "updated_at"])
        return Response(MistakeSerializer(progress).data)


class LeaderboardView(APIView):
    def get(self, request):
        subject_id = request.query_params.get("subject")
        if subject_id:
            subject = get_object_or_404(Subject, pk=subject_id)
            rows = list(leaderboard_queryset(subject=subject)[:100])
            for index, row in enumerate(rows, start=1):
                row.rank = index
            return Response(LeaderboardEntrySerializer(rows, many=True).data)

        rows = (
            UserSubjectStats.objects.filter(total_answered__gt=0)
            .values("user_id", "user__username")
            .annotate(
                points=Sum("points"),
                total_answered=Sum("total_answered"),
                correct_answers=Sum("correct_answers"),
                unique_questions_seen=Sum("unique_questions_seen"),
            )
            .order_by("-points", "-unique_questions_seen", "-correct_answers", "user__username")[:100]
        )
        payload = []
        for index, row in enumerate(rows, start=1):
            total = row["total_answered"] or 0
            correct = row["correct_answers"] or 0
            payload.append(
                {
                    "rank": index,
                    "username": row["user__username"],
                    "points": row["points"] or 0,
                    "total_answered": total,
                    "winrate": round(correct * 100 / total, 2) if total else 0,
                    "unique_questions_seen": row["unique_questions_seen"] or 0,
                    "subject_id": None,
                }
            )
        return Response(payload)


class ImportQuestionsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        summary = import_questions_from_base(settings.BASE_QUESTIONS_DIR)
        latest = ImportRun.objects.first()
        return Response(
            {
                "summary": summary.as_dict(),
                "run": ImportRunSerializer(latest).data if latest else None,
            }
        )


class ImportStatusView(APIView):
    def get(self, request):
        latest = ImportRun.objects.first()
        if not latest:
            return Response({"latest": None})
        return Response({"latest": ImportRunSerializer(latest).data})
