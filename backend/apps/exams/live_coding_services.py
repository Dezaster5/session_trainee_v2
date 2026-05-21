import random
import re
from difflib import SequenceMatcher

from django.db import transaction
from django.utils import timezone

from .models import (
    DailyActivity,
    LiveCodingAttempt,
    LiveCodingSession,
    LiveCodingSessionTask,
    LiveCodingTask,
    UserLiveCodingProgress,
    UserSubjectStats,
)
from .services import resolve_question_count, weighted_sample_without_replacement


LIVE_CODING_POINT_CAP = 20
SOLVED_THRESHOLD = 80
COMMAND_LANGUAGES = {"shell", "bash", "sh", "zsh", "powershell", "terminal", "cli", "docker", "git"}
TOKEN_RE = re.compile(r"@[A-Za-z_][\w.]*|[A-Za-z_][\w.]*|==|!=|<=|>=|&&|\|\||[{}()[\].,;:=<>/+*%-]")
WHITESPACE_RE = re.compile(r"\s+")
COMMENT_RE = re.compile(r"//.*?$|/\*.*?\*/|#.*?$", re.MULTILINE | re.DOTALL)


def normalize_command_answer(value):
    normalized = WHITESPACE_RE.sub(" ", (value or "").strip().lower())
    return normalized.rstrip(";")


def normalize_code_answer(value):
    without_comments = COMMENT_RE.sub(" ", value or "")
    return WHITESPACE_RE.sub(" ", without_comments).strip()


def tokenize(value):
    return TOKEN_RE.findall(normalize_code_answer(value))


def calculate_text_similarity(a, b):
    left = normalize_code_answer(a).casefold()
    right = normalize_code_answer(b).casefold()
    if not left and not right:
        return 100.0
    if not left or not right:
        return 0.0
    return round(SequenceMatcher(None, left, right).ratio() * 100, 2)


def calculate_token_similarity(a, b):
    expected_tokens = tokenize(b)
    submitted_tokens = tokenize(a)
    if not expected_tokens and not submitted_tokens:
        return 100.0
    if not expected_tokens or not submitted_tokens:
        return 0.0

    expected_set = set(token.casefold() for token in expected_tokens)
    submitted_set = set(token.casefold() for token in submitted_tokens)
    overlap = len(expected_set & submitted_set)
    precision = overlap / len(submitted_set) if submitted_set else 0
    recall = overlap / len(expected_set) if expected_set else 0
    if precision + recall == 0:
        return 0.0
    return round((2 * precision * recall / (precision + recall)) * 100, 2)


def calculate_keyword_similarity(a, b, language):
    expected = normalize_code_answer(b)
    submitted = normalize_code_answer(a)
    language = (language or "").casefold()
    keywords = {
        "class",
        "public",
        "private",
        "protected",
        "return",
        "extends",
        "implements",
        "interface",
        "new",
        "void",
    }
    if "java" in language or "spring" in language:
        keywords.update(
            {
                "@RestController",
                "@Controller",
                "@GetMapping",
                "@PostMapping",
                "@RequestMapping",
                "@Service",
                "@Repository",
                "@Entity",
                "@Autowired",
                "@SpringBootApplication",
                "@Bean",
                "@Id",
                "@GeneratedValue",
            }
        )

    expected_keywords = {keyword for keyword in keywords if keyword.casefold() in expected.casefold()}
    if not expected_keywords:
        return 100.0
    matched = {keyword for keyword in expected_keywords if keyword.casefold() in submitted.casefold()}
    return round(len(matched) * 100 / len(expected_keywords), 2)


def calculate_final_similarity(submitted, expected, language, check_type):
    language_key = (language or "").casefold()
    check_key = (check_type or "").casefold()

    if language_key in COMMAND_LANGUAGES or "command" in check_key:
        submitted_normalized = normalize_command_answer(submitted)
        expected_normalized = normalize_command_answer(expected)
        if submitted_normalized == expected_normalized:
            return 100.0

        submitted_tokens = set(submitted_normalized.split())
        expected_tokens = set(expected_normalized.split())
        token_score = 0.0
        if expected_tokens:
            token_score = len(submitted_tokens & expected_tokens) * 100 / len(expected_tokens)
        sequence_score = calculate_text_similarity(submitted_normalized, expected_normalized)
        return round(max(sequence_score, token_score * 0.92), 2)

    text_score = calculate_text_similarity(submitted, expected)
    token_score = calculate_token_similarity(submitted, expected)
    keyword_score = calculate_keyword_similarity(submitted, expected, language)
    if normalize_code_answer(submitted).casefold() == normalize_code_answer(expected).casefold():
        return 100.0
    return round(text_score * 0.45 + token_score * 0.4 + keyword_score * 0.15, 2)


def evaluate_live_coding_answer(submitted, expected, language, check_type):
    similarity_score = calculate_final_similarity(submitted, expected, language, check_type)
    if similarity_score >= 90:
        status = LiveCodingAttempt.STATUS_EXCELLENT
        feedback = "Excellent match. Core command or code structure is correct."
    elif similarity_score >= 75:
        status = LiveCodingAttempt.STATUS_GOOD
        feedback = "Good answer. Minor syntax or structural differences remain."
    elif similarity_score >= 50:
        status = LiveCodingAttempt.STATUS_NEEDS_PRACTICE
        feedback = "Partially correct. Review the expected structure and key tokens."
    else:
        status = LiveCodingAttempt.STATUS_WRONG
        feedback = "Low similarity. Compare the command or required code elements carefully."

    return {
        "similarity_score": similarity_score,
        "status": status,
        "feedback": feedback,
    }


def live_task_weight(task, progress, mode):
    if progress is None:
        return 7.0

    weight = 1.0
    if not progress.is_solved:
        weight += 4.0
    if progress.best_similarity < SOLVED_THRESHOLD:
        weight += (SOLVED_THRESHOLD - progress.best_similarity) / 10
    if progress.attempts_count:
        weight += 3 / (progress.attempts_count + 1)
    if progress.last_attempt_at:
        age_days = (timezone.now() - progress.last_attempt_at).days
        weight += min(age_days * 0.1, 3.0)
    if mode == LiveCodingSession.MODE_RARE:
        weight += 5 / (progress.attempts_count + 1)
    if mode == LiveCodingSession.MODE_HARD:
        weight += max(0, (85 - progress.best_similarity) / 10)
    if progress.is_solved and progress.best_similarity >= 90:
        weight *= 0.35
    return max(weight, 0.05)


def live_base_queryset(user, subject, mode, topic_ids=None):
    queryset = LiveCodingTask.objects.filter(subject=subject).select_related("subject", "topic")
    topic_ids = [int(topic_id) for topic_id in (topic_ids or []) if str(topic_id).strip()]
    if topic_ids:
        queryset = queryset.filter(topic_id__in=topic_ids)

    if mode == LiveCodingSession.MODE_NEW:
        return queryset.exclude(progress_records__user=user)
    if mode == LiveCodingSession.MODE_MISTAKES:
        return queryset.filter(progress_records__user=user, progress_records__attempts_count__gt=0).filter(
            progress_records__is_solved=False
        )
    if mode == LiveCodingSession.MODE_HARD:
        return queryset.filter(progress_records__user=user).filter(
            progress_records__best_similarity__lt=SOLVED_THRESHOLD
        )
    return queryset


def select_live_coding_tasks(user, subject, mode, requested_count, topic_ids=None):
    queryset = live_base_queryset(user, subject, mode, topic_ids=topic_ids)
    tasks = list(queryset)
    if not tasks:
        return []

    progress_map = {
        progress.task_id: progress
        for progress in UserLiveCodingProgress.objects.filter(
            user=user,
            task__subject=subject,
        )
    }
    count = resolve_question_count(requested_count, len(tasks))

    if mode in {LiveCodingSession.MODE_NEW, LiveCodingSession.MODE_REVIEW_ALL}:
        random.shuffle(tasks)
        return tasks[:count]

    if mode == LiveCodingSession.MODE_RARE:
        tasks.sort(key=lambda item: progress_map.get(item.id).attempts_count if progress_map.get(item.id) else 0)
        tasks = tasks[: max(count * 3, count)]

    return weighted_sample_without_replacement(
        tasks,
        count,
        lambda task: live_task_weight(task, progress_map.get(task.id), mode),
    )


@transaction.atomic
def create_live_coding_session(user, subject, mode, requested_count, topic_ids=None):
    topic_ids = [int(topic_id) for topic_id in (topic_ids or []) if str(topic_id).strip()]
    tasks = select_live_coding_tasks(user, subject, mode, requested_count, topic_ids=topic_ids)
    if not tasks:
        return None

    session = LiveCodingSession.objects.create(
        user=user,
        subject=subject,
        topic_id=topic_ids[0] if len(topic_ids) == 1 else None,
        mode=mode,
        total_tasks=len(tasks),
    )
    LiveCodingSessionTask.objects.bulk_create(
        [
            LiveCodingSessionTask(session=session, task=task, order=index)
            for index, task in enumerate(tasks, start=1)
        ]
    )
    return session


def get_next_live_coding_task(session):
    attempted_task_ids = session.attempts.values_list("task_id", flat=True)
    return (
        session.session_tasks.exclude(task_id__in=attempted_task_ids)
        .select_related("task", "task__subject", "task__topic")
        .order_by("order")
        .first()
    )


def calculate_live_coding_points(progress, similarity_score):
    if similarity_score < 50:
        return -1

    remaining_credit = max(0, LIVE_CODING_POINT_CAP - progress.points_earned)
    if similarity_score >= 90:
        base = 15 if progress.attempts_count == 0 else 5
    elif similarity_score >= 75:
        base = 8 if progress.attempts_count == 0 else 3
    else:
        base = 3
    return min(base, remaining_credit)


@transaction.atomic
def submit_live_coding_attempt(session, task_id, submitted_code, time_spent=0):
    if session.status != LiveCodingSession.STATUS_ACTIVE:
        raise ValueError("Live coding session is already finished")

    session_task = session.session_tasks.filter(task_id=task_id).select_related("task").first()
    if not session_task:
        raise ValueError("Task does not belong to this live coding session")
    if LiveCodingAttempt.objects.filter(session=session, task_id=task_id).exists():
        raise ValueError("Task has already been attempted in this live coding session")

    task = session_task.task
    evaluation = evaluate_live_coding_answer(
        submitted=submitted_code,
        expected=task.expected_solution,
        language=task.language,
        check_type=task.check_type,
    )
    similarity_score = evaluation["similarity_score"]
    now = timezone.now()

    progress, _created = UserLiveCodingProgress.objects.select_for_update().get_or_create(
        user=session.user,
        task=task,
    )
    was_solved = progress.is_solved
    points = calculate_live_coding_points(progress, similarity_score)
    solved_now = similarity_score >= SOLVED_THRESHOLD

    attempt = LiveCodingAttempt.objects.create(
        session=session,
        task=task,
        submitted_code=submitted_code or "",
        similarity_score=similarity_score,
        status=evaluation["status"],
        points_awarded=points,
        feedback=evaluation["feedback"],
        time_spent=max(int(time_spent or 0), 0),
    )

    progress.attempts_count += 1
    progress.last_similarity = similarity_score
    progress.best_similarity = max(progress.best_similarity, similarity_score)
    progress.is_solved = progress.is_solved or solved_now
    progress.last_submitted_code = submitted_code or ""
    progress.last_attempt_at = now
    if solved_now and not progress.first_solved_at:
        progress.first_solved_at = now
    if points > 0:
        progress.points_earned += points
    progress.save()

    stats, _ = UserSubjectStats.objects.select_for_update().get_or_create(
        user=session.user,
        subject=session.subject,
    )
    old_attempts = stats.live_coding_attempts
    stats.live_coding_attempts = old_attempts + 1
    stats.average_live_coding_similarity = round(
        ((stats.average_live_coding_similarity * old_attempts) + similarity_score)
        / stats.live_coding_attempts,
        2,
    )
    if solved_now and not was_solved:
        stats.live_coding_solved += 1
    stats.points += points
    stats.last_activity_at = now
    stats.save()

    activity, _ = DailyActivity.objects.select_for_update().get_or_create(
        user=session.user,
        day=now.date(),
    )
    activity.total_answers += 1
    if solved_now:
        activity.correct_answers += 1
    else:
        activity.wrong_answers += 1
    activity.points += points
    activity.save()

    old_session_attempts = session.attempts.exclude(pk=attempt.pk).count()
    session.score += points
    session.average_similarity = round(
        ((session.average_similarity * old_session_attempts) + similarity_score)
        / (old_session_attempts + 1),
        2,
    )
    session.save(update_fields=["score", "average_similarity"])

    attempted_tasks = session.attempts.values("task_id").distinct().count()
    if attempted_tasks >= session.total_tasks:
        session.finish()

    return attempt, progress
