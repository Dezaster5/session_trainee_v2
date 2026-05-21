import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from .models import (
    AnswerVariant,
    DailyActivity,
    Question,
    TestAnswer,
    TestSession,
    TestSessionQuestion,
    UserQuestionProgress,
    UserSubjectStats,
)


DEFAULT_TEST_SIZE = 10
MAX_CUSTOM_TEST_SIZE = 200
QUESTION_POINT_CAP = 16


def resolve_question_count(raw_count, available_count):
    if raw_count in (None, "", "default"):
        return min(DEFAULT_TEST_SIZE, available_count)
    if raw_count == "all":
        return available_count
    try:
        count = int(raw_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("question_count must be one of 5, 10, 20, 50, all, or a positive integer") from exc
    count = max(1, min(count, MAX_CUSTOM_TEST_SIZE))
    return min(count, available_count)


def progress_winrate(progress):
    if not progress:
        return None
    total = progress.times_correct + progress.times_wrong
    if total == 0:
        return None
    return progress.times_correct / total


def question_weight(question, progress, mode):
    if progress is None:
        return 8.0 if mode in {TestSession.MODE_RANDOM, TestSession.MODE_SPACED} else 5.0

    total_answers = progress.times_correct + progress.times_wrong
    winrate = progress_winrate(progress)
    weight = max(0.35, progress.personal_weight)

    if progress.times_wrong:
        weight += min(progress.times_wrong * 1.7, 7.0)
    if winrate is not None and winrate < 0.65:
        weight += (0.65 - winrate) * 6
    if progress.current_streak >= 3:
        weight *= 0.55
    if progress.times_correct >= 4 and progress.times_wrong == 0:
        weight *= 0.35
    if progress.is_mastered:
        weight *= 0.25

    if progress.last_seen_at:
        age_days = (timezone.now() - progress.last_seen_at).days
        weight += min(age_days * 0.08, 4.0)

    if mode == TestSession.MODE_RARE:
        weight += 6 / (progress.times_seen + 1)
    elif mode == TestSession.MODE_HARD:
        weight += (1 - (winrate or 0.3)) * 4
    elif mode == TestSession.MODE_SPACED:
        if progress.last_wrong_at and timezone.now() - progress.last_wrong_at > timedelta(hours=2):
            weight += 4
        if progress.current_streak >= 2 and total_answers >= 2:
            weight *= 0.65

    return max(weight, 0.05)


def weighted_sample_without_replacement(items, count, weight_getter):
    pool = list(items)
    selected = []
    while pool and len(selected) < count:
        weights = [weight_getter(item) for item in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]
        selected.append(chosen)
        pool.remove(chosen)
    return selected


def normalized_topic_ids(topic_ids):
    if not topic_ids:
        return []
    return [int(topic_id) for topic_id in topic_ids if str(topic_id).strip()]


def base_queryset_for_mode(user, subject, mode, topic_ids=None):
    queryset = Question.objects.filter(subject=subject).prefetch_related("variants")
    topic_ids = normalized_topic_ids(topic_ids)
    if topic_ids:
        queryset = queryset.filter(topic_id__in=topic_ids)

    if mode == TestSession.MODE_NEW:
        return queryset.exclude(progress_records__user=user)
    if mode == TestSession.MODE_MISTAKES:
        return queryset.filter(progress_records__user=user, progress_records__times_wrong__gt=0)
    if mode == TestSession.MODE_HARD:
        return queryset.filter(
            progress_records__user=user,
        ).filter(
            Q(progress_records__times_wrong__gt=0)
            | Q(progress_records__personal_weight__gte=1.5)
            | Q(progress_records__current_streak__lt=0)
        )
    return queryset


def select_questions(user, subject, mode, requested_count, topic_ids=None):
    queryset = base_queryset_for_mode(user, subject, mode, topic_ids=topic_ids)
    questions = list(queryset)

    if not questions:
        return []

    progress_map = {
        progress.question_id: progress
        for progress in UserQuestionProgress.objects.filter(
            user=user,
            question__subject=subject,
        )
    }
    count = resolve_question_count(requested_count, len(questions))

    if mode == TestSession.MODE_NEW:
        random.shuffle(questions)
        return questions[:count]

    if mode == TestSession.MODE_REVIEW_ALL:
        random.shuffle(questions)
        return questions[:count]

    if mode == TestSession.MODE_RARE:
        questions.sort(key=lambda item: progress_map.get(item.id).times_seen if progress_map.get(item.id) else 0)
        rare_pool = questions[: max(count * 3, count)]
        return weighted_sample_without_replacement(
            rare_pool,
            count,
            lambda question: question_weight(question, progress_map.get(question.id), mode),
        )

    return weighted_sample_without_replacement(
        questions,
        count,
        lambda question: question_weight(question, progress_map.get(question.id), mode),
    )


@transaction.atomic
def create_test_session(user, subject, mode, requested_count, topic_ids=None):
    questions = select_questions(user, subject, mode, requested_count, topic_ids=topic_ids)
    if not questions:
        return None

    session = TestSession.objects.create(
        user=user,
        subject=subject,
        mode=mode,
        total_questions=len(questions),
    )
    TestSessionQuestion.objects.bulk_create(
        [
            TestSessionQuestion(session=session, question=question, order=index)
            for index, question in enumerate(questions, start=1)
        ]
    )
    mark_questions_seen(user, subject, questions)
    return session


def get_next_question(session):
    answered_ids = session.answers.values_list("question_id", flat=True)
    return (
        session.session_questions.exclude(question_id__in=answered_ids)
        .select_related("question")
        .prefetch_related("question__variants")
        .order_by("order")
        .first()
    )


def calculate_points(progress, is_correct):
    if not is_correct:
        return -2

    remaining_credit = max(0, QUESTION_POINT_CAP - progress.points_earned)
    if remaining_credit == 0:
        return 0

    if progress.times_correct == 0:
        base = 10
    elif progress.times_wrong > 0 or progress.personal_weight >= 1.5:
        base = 3
    else:
        base = 1

    next_streak = progress.current_streak + 1
    streak_bonus = 0
    if next_streak in (5, 10, 20):
        streak_bonus = {5: 2, 10: 5, 20: 10}[next_streak]

    return min(base + streak_bonus, remaining_credit)


def mark_questions_seen(user, subject, questions, now=None):
    now = now or timezone.now()
    new_unique_count = 0

    for question in questions:
        progress, created = UserQuestionProgress.objects.select_for_update().get_or_create(
            user=user,
            question=question,
            defaults={
                "times_seen": 1,
                "last_seen_at": now,
            },
        )
        if created:
            new_unique_count += 1
            continue

        if progress.times_seen == 0:
            new_unique_count += 1
        progress.times_seen = F("times_seen") + 1
        progress.last_seen_at = now
        progress.save(update_fields=["times_seen", "last_seen_at", "updated_at"])

    if new_unique_count:
        stats, _ = UserSubjectStats.objects.select_for_update().get_or_create(
            user=user,
            subject=subject,
        )
        stats.unique_questions_seen = F("unique_questions_seen") + new_unique_count
        stats.last_activity_at = now
        stats.save(update_fields=["unique_questions_seen", "last_activity_at", "updated_at"])


def ensure_question_seen_for_answer(user, question_id, now):
    progress, created = UserQuestionProgress.objects.select_for_update().get_or_create(
        user=user,
        question_id=question_id,
        defaults={
            "times_seen": 1,
            "last_seen_at": now,
        },
    )
    if created:
        return progress, 1

    if progress.times_seen == 0:
        progress.times_seen = F("times_seen") + 1
        progress.last_seen_at = now
        progress.save(update_fields=["times_seen", "last_seen_at", "updated_at"])
        progress.refresh_from_db()
        return progress, 1

    return progress, 0


def apply_progress_update(progress, is_correct, points, now):
    if is_correct:
        next_streak = max(progress.current_streak, 0) + 1
        progress.times_correct = F("times_correct") + 1
        progress.current_streak = next_streak
        progress.best_streak = max(progress.best_streak, next_streak)
        progress.last_correct_at = now
        progress.personal_weight = max(0.2, progress.personal_weight * 0.72)
        if next_streak >= 4:
            progress.is_mastered = True
        progress.points_earned = F("points_earned") + max(points, 0)
    else:
        progress.times_wrong = F("times_wrong") + 1
        progress.current_streak = min(progress.current_streak, 0) - 1
        progress.last_wrong_at = now
        progress.is_mastered = False
        progress.personal_weight = min(6.0, progress.personal_weight + 1.15)

    progress.save()
    progress.refresh_from_db()


@transaction.atomic
def record_answer(session, question_id, selected_variant_id, time_spent=0):
    if session.status != TestSession.STATUS_ACTIVE:
        raise ValueError("Test session is already finished")

    session_question = session.session_questions.filter(question_id=question_id).select_related("question").first()
    if not session_question:
        raise ValueError("Question does not belong to this test session")

    if TestAnswer.objects.filter(session=session, question_id=question_id).exists():
        raise ValueError("Question has already been answered in this session")

    selected_variant = AnswerVariant.objects.filter(
        id=selected_variant_id,
        question_id=question_id,
    ).first()
    if not selected_variant:
        raise ValueError("Selected variant does not belong to this question")

    now = timezone.now()
    progress, unique_seen_increment = ensure_question_seen_for_answer(
        user=session.user,
        question_id=question_id,
        now=now,
    )
    points = calculate_points(progress, selected_variant.is_correct)
    apply_progress_update(progress, selected_variant.is_correct, points, now)

    answer = TestAnswer.objects.create(
        session=session,
        question_id=question_id,
        selected_variant=selected_variant,
        is_correct=selected_variant.is_correct,
        time_spent=max(int(time_spent or 0), 0),
        points_awarded=points,
    )

    stats, _ = UserSubjectStats.objects.select_for_update().get_or_create(
        user=session.user,
        subject=session.subject,
    )
    stats.total_answered = F("total_answered") + 1
    stats.unique_questions_seen = F("unique_questions_seen") + unique_seen_increment
    stats.correct_answers = F("correct_answers") + (1 if selected_variant.is_correct else 0)
    stats.wrong_answers = F("wrong_answers") + (0 if selected_variant.is_correct else 1)
    stats.points = F("points") + points
    stats.last_activity_at = now
    stats.save()

    activity, _ = DailyActivity.objects.select_for_update().get_or_create(
        user=session.user,
        day=now.date(),
    )
    activity.total_answers = F("total_answers") + 1
    activity.correct_answers = F("correct_answers") + (1 if selected_variant.is_correct else 0)
    activity.wrong_answers = F("wrong_answers") + (0 if selected_variant.is_correct else 1)
    activity.points = F("points") + points
    activity.save()

    session.score = F("score") + points
    session.correct_count = F("correct_count") + (1 if selected_variant.is_correct else 0)
    session.wrong_count = F("wrong_count") + (0 if selected_variant.is_correct else 1)
    session.save()
    session.refresh_from_db()

    if session.answers.count() >= session.total_questions:
        session.finish()

    return answer, progress


def leaderboard_queryset(subject=None):
    queryset = UserSubjectStats.objects.filter(total_answered__gt=0).select_related("user", "subject")
    if subject is not None:
        queryset = queryset.filter(subject=subject)
    return queryset.order_by("-points", "-unique_questions_seen", "-correct_answers", "user__username")


def aggregate_user_totals(user):
    stats = UserSubjectStats.objects.filter(user=user).aggregate(
        total_answered=Sum("total_answered"),
        correct_answers=Sum("correct_answers"),
        wrong_answers=Sum("wrong_answers"),
        points=Sum("points"),
        unique_questions_seen=Sum("unique_questions_seen"),
        live_coding_attempts=Sum("live_coding_attempts"),
        live_coding_solved=Sum("live_coding_solved"),
    )
    total = stats["total_answered"] or 0
    correct = stats["correct_answers"] or 0
    stats = {key: value or 0 for key, value in stats.items()}
    stats["winrate"] = round(correct * 100 / total, 2) if total else 0
    similarity_rows = UserSubjectStats.objects.filter(
        user=user,
        live_coding_attempts__gt=0,
    ).values("live_coding_attempts", "average_live_coding_similarity")
    total_attempts = sum(row["live_coding_attempts"] for row in similarity_rows)
    weighted_similarity = sum(
        row["average_live_coding_similarity"] * row["live_coding_attempts"]
        for row in similarity_rows
    )
    stats["average_live_coding_similarity"] = round(weighted_similarity / total_attempts, 2) if total_attempts else 0
    return stats


def subject_progress_rows(user):
    rows = []
    stats_map = {
        stat.subject_id: stat
        for stat in UserSubjectStats.objects.filter(user=user).select_related("subject")
    }
    from .models import Subject

    subjects = Subject.objects.annotate(
        question_count=Count("questions", distinct=True),
        live_coding_count=Count("live_coding_tasks", distinct=True),
    ).order_by("name")
    for subject in subjects:
        stat = stats_map.get(subject.id)
        question_count = subject.question_count or 0
        live_coding_count = subject.live_coding_count or 0
        unique_seen = stat.unique_questions_seen if stat else 0
        rows.append(
            {
                "subject_id": subject.id,
                "subject_name": subject.name,
                "slug": subject.slug,
                "question_count": question_count,
                "live_coding_count": live_coding_count,
                "unique_questions_seen": unique_seen,
                "completion_percent": round(unique_seen * 100 / question_count, 2) if question_count else 0,
                "total_answered": stat.total_answered if stat else 0,
                "correct_answers": stat.correct_answers if stat else 0,
                "wrong_answers": stat.wrong_answers if stat else 0,
                "live_coding_attempts": stat.live_coding_attempts if stat else 0,
                "live_coding_solved": stat.live_coding_solved if stat else 0,
                "average_live_coding_similarity": stat.average_live_coding_similarity if stat else 0,
                "winrate": stat.winrate if stat else 0,
                "points": stat.points if stat else 0,
                "last_activity_at": stat.last_activity_at if stat else None,
            }
        )
    return rows
