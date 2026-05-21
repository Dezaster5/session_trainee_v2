from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .importer import import_questions_from_base
from .live_coding_services import create_live_coding_session, submit_live_coding_attempt
from .models import (
    DailyActivity,
    ImportRun,
    LiveCodingSession,
    LiveCodingTask,
    Subject,
    TestSession,
    Topic,
    UserLiveCodingProgress,
    UserQuestionProgress,
    UserSubjectStats,
)
from .serializers import (
    ImportRunSerializer,
    LeaderboardEntrySerializer,
    LiveCodingAttemptSerializer,
    LiveCodingResultSerializer,
    LiveCodingSessionStateSerializer,
    LiveCodingStartSerializer,
    LiveCodingSubmitSerializer,
    LiveCodingTaskSerializer,
    LiveCodingWeakTaskSerializer,
    MistakeSerializer,
    RegisterSerializer,
    SubjectDetailSerializer,
    SubjectSerializer,
    TestAnswerInputSerializer,
    TestAnswerResultSerializer,
    TestResultSerializer,
    TestSessionStateSerializer,
    TestStartSerializer,
    TopicSerializer,
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
            live_coding_count=Count("live_coding_tasks", distinct=True),
            users_count=Count("questions__progress_records__user", distinct=True),
            seen_records_count=Count("questions__progress_records", distinct=True),
        ).order_by("name")


class SubjectDetailView(generics.RetrieveAPIView):
    serializer_class = SubjectDetailSerializer
    queryset = Subject.objects.annotate(
        question_count=Count("questions", distinct=True),
        live_coding_count=Count("live_coding_tasks", distinct=True),
        users_count=Count("questions__progress_records__user", distinct=True),
        seen_records_count=Count("questions__progress_records", distinct=True),
    )


class SubjectTopicsView(generics.ListAPIView):
    serializer_class = TopicSerializer

    def get_queryset(self):
        subject = get_object_or_404(Subject, pk=self.kwargs["pk"])
        return subject.topics.annotate(
            question_count=Count("questions", distinct=True),
            live_coding_count=Count("live_coding_tasks", distinct=True),
        ).order_by("type", "order", "title")


class TestStartView(APIView):
    def post(self, request):
        serializer = TestStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject = get_object_or_404(Subject, pk=serializer.validated_data["subject_id"])
        topic_ids = serializer.validated_data.get("topic_ids") or []
        if topic_ids:
            valid_count = Topic.objects.filter(
                subject=subject,
                type=Topic.TYPE_THEORY,
                id__in=topic_ids,
            ).count()
            if valid_count != len(topic_ids):
                return Response(
                    {"detail": "One or more selected theory topics do not belong to this subject."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        session = create_test_session(
            user=request.user,
            subject=subject,
            mode=serializer.validated_data["mode"],
            requested_count=serializer.validated_data["question_count"],
            topic_ids=topic_ids,
        )
        if session is None:
            return Response(
                {"detail": "No questions available for the selected mode or topics."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(TestSessionStateSerializer(session, context={"request": request}).data, status=status.HTTP_201_CREATED)


class TestSessionDetailView(generics.RetrieveAPIView):
    serializer_class = TestSessionStateSerializer

    def get_queryset(self):
        return TestSession.objects.filter(user=self.request.user).select_related("subject").prefetch_related(
            "session_questions__question__topic",
            "session_questions__question__variants",
        )


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
            .prefetch_related("answers__question__topic", "answers__question__variants", "answers__selected_variant")
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
        live_weak_tasks = (
            UserLiveCodingProgress.objects.filter(user=request.user, attempts_count__gt=0)
            .filter(Q(best_similarity__lt=80) | Q(is_solved=False))
            .select_related("task", "task__subject", "task__topic")
            .order_by("is_solved", "best_similarity", "-last_attempt_at")[:6]
        )
        recent_live_sessions = LiveCodingSession.objects.filter(user=request.user).select_related("subject")[:5]
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
                "live_coding_weak_tasks": LiveCodingWeakTaskSerializer(live_weak_tasks, many=True, context={"request": request}).data,
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
                "recent_live_coding_sessions": [
                    {
                        "id": session.id,
                        "subject": session.subject.name,
                        "mode": session.mode,
                        "status": session.status,
                        "score": session.score,
                        "average_similarity": session.average_similarity,
                        "total_tasks": session.total_tasks,
                        "started_at": session.started_at,
                        "finished_at": session.finished_at,
                    }
                    for session in recent_live_sessions
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
            .select_related("question", "question__subject", "question__topic")
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
        leaderboard_type = request.query_params.get("type", "all")
        if subject_id:
            subject = get_object_or_404(Subject, pk=subject_id)
            rows_query = UserSubjectStats.objects.filter(subject=subject).select_related("user", "subject")
            if leaderboard_type == "live_coding":
                rows_query = rows_query.filter(live_coding_attempts__gt=0).order_by(
                    "-live_coding_solved",
                    "-average_live_coding_similarity",
                    "-points",
                    "user__username",
                )
            elif leaderboard_type == "theory":
                rows_query = leaderboard_queryset(subject=subject)
            else:
                rows_query = rows_query.filter(Q(total_answered__gt=0) | Q(live_coding_attempts__gt=0)).order_by(
                    "-points",
                    "-unique_questions_seen",
                    "-live_coding_solved",
                    "user__username",
                )
            rows = list(rows_query[:100])
            for index, row in enumerate(rows, start=1):
                row.rank = index
            return Response(LeaderboardEntrySerializer(rows, many=True).data)

        base_rows = UserSubjectStats.objects.all()
        if leaderboard_type == "live_coding":
            base_rows = base_rows.filter(live_coding_attempts__gt=0)
            ordering = ["-live_coding_solved", "-average_live_coding_similarity", "-points", "user__username"]
        elif leaderboard_type == "theory":
            base_rows = base_rows.filter(total_answered__gt=0)
            ordering = ["-points", "-unique_questions_seen", "-correct_answers", "user__username"]
        else:
            base_rows = base_rows.filter(Q(total_answered__gt=0) | Q(live_coding_attempts__gt=0))
            ordering = ["-points", "-unique_questions_seen", "-live_coding_solved", "user__username"]

        rows = (
            base_rows
            .values("user_id", "user__username")
            .annotate(
                points=Sum("points"),
                total_answered=Sum("total_answered"),
                correct_answers=Sum("correct_answers"),
                unique_questions_seen=Sum("unique_questions_seen"),
                live_coding_attempts=Sum("live_coding_attempts"),
                live_coding_solved=Sum("live_coding_solved"),
                average_live_coding_similarity=Avg(
                    "average_live_coding_similarity",
                    filter=Q(live_coding_attempts__gt=0),
                ),
            )
            .order_by(*ordering)[:100]
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
                    "live_coding_attempts": row["live_coding_attempts"] or 0,
                    "live_coding_solved": row["live_coding_solved"] or 0,
                    "average_live_coding_similarity": round(row["average_live_coding_similarity"] or 0, 2),
                    "subject_id": None,
                }
            )
        return Response(payload)


class LiveCodingTaskListView(generics.ListAPIView):
    serializer_class = LiveCodingTaskSerializer

    def get_queryset(self):
        queryset = LiveCodingTask.objects.select_related("subject", "topic")
        subject_id = self.request.query_params.get("subject")
        topic_id = self.request.query_params.get("topic")
        task_status = self.request.query_params.get("status", "all")

        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        if topic_id:
            queryset = queryset.filter(topic_id=topic_id)

        if task_status == "solved":
            queryset = queryset.filter(progress_records__user=self.request.user, progress_records__is_solved=True)
        elif task_status == "unsolved":
            queryset = queryset.exclude(progress_records__user=self.request.user, progress_records__is_solved=True)
        elif task_status == "weak":
            queryset = queryset.filter(progress_records__user=self.request.user, progress_records__attempts_count__gt=0).filter(
                Q(progress_records__best_similarity__lt=80) | Q(progress_records__is_solved=False)
            )

        ordering = self.request.query_params.get("ordering", "id")
        allowed = {"id", "-id", "language", "-language", "difficulty", "-difficulty", "created_at", "-created_at"}
        if ordering not in allowed:
            ordering = "id"
        return queryset.distinct().order_by(ordering)


class LiveCodingStartView(APIView):
    def post(self, request):
        serializer = LiveCodingStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subject = get_object_or_404(Subject, pk=serializer.validated_data["subject_id"])
        topic_ids = serializer.validated_data.get("topic_ids") or []
        if topic_ids:
            valid_count = Topic.objects.filter(
                subject=subject,
                type=Topic.TYPE_LIVE_CODING,
                id__in=topic_ids,
            ).count()
            if valid_count != len(topic_ids):
                return Response(
                    {"detail": "One or more selected live coding topics do not belong to this subject."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        session = create_live_coding_session(
            user=request.user,
            subject=subject,
            mode=serializer.validated_data["mode"],
            requested_count=serializer.validated_data["task_count"],
            topic_ids=topic_ids,
        )
        if session is None:
            return Response(
                {"detail": "No live coding tasks available for the selected mode or topics."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(LiveCodingSessionStateSerializer(session, context={"request": request}).data, status=status.HTTP_201_CREATED)


class LiveCodingSessionDetailView(generics.RetrieveAPIView):
    serializer_class = LiveCodingSessionStateSerializer

    def get_queryset(self):
        return LiveCodingSession.objects.filter(user=self.request.user).select_related("subject", "topic").prefetch_related(
            "session_tasks__task__topic",
            "attempts__task__topic",
        )


class LiveCodingSubmitView(APIView):
    def post(self, request, pk):
        session = get_object_or_404(
            LiveCodingSession.objects.select_related("subject", "user"),
            pk=pk,
            user=request.user,
        )
        serializer = LiveCodingSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            attempt, _progress = submit_live_coding_attempt(
                session=session,
                task_id=serializer.validated_data["task_id"],
                submitted_code=serializer.validated_data["submitted_code"],
                time_spent=serializer.validated_data.get("time_spent", 0),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        attempt = attempt.__class__.objects.select_related("task", "task__subject", "task__topic", "session").get(pk=attempt.pk)
        session.refresh_from_db()
        return Response(
            {
                "attempt": LiveCodingAttemptSerializer(attempt, context={"request": request}).data,
                "session": LiveCodingSessionStateSerializer(session, context={"request": request}).data,
                "has_next": session.status == LiveCodingSession.STATUS_ACTIVE,
            }
        )


class LiveCodingResultView(generics.RetrieveAPIView):
    serializer_class = LiveCodingResultSerializer

    def get_queryset(self):
        return (
            LiveCodingSession.objects.filter(user=self.request.user)
            .select_related("subject", "topic")
            .prefetch_related("attempts__task__subject", "attempts__task__topic")
        )


class LiveCodingMistakesView(generics.ListAPIView):
    serializer_class = LiveCodingWeakTaskSerializer

    def get_queryset(self):
        queryset = (
            UserLiveCodingProgress.objects.filter(user=self.request.user, attempts_count__gt=0)
            .filter(Q(best_similarity__lt=80) | Q(is_solved=False))
            .select_related("task", "task__subject", "task__topic")
        )
        subject_id = self.request.query_params.get("subject")
        if subject_id:
            queryset = queryset.filter(task__subject_id=subject_id)

        ordering = self.request.query_params.get("ordering", "best_similarity")
        allowed = {
            "best_similarity",
            "-best_similarity",
            "last_attempt_at",
            "-last_attempt_at",
            "attempts_count",
            "-attempts_count",
        }
        if ordering not in allowed:
            ordering = "best_similarity"
        return queryset.order_by(ordering)


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
