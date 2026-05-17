import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("running", "Running"), ("success", "Success"), ("failed", "Failed")], default="running", max_length=16)),
                ("base_dir", models.CharField(blank=True, max_length=500)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("subjects_found", models.PositiveIntegerField(default=0)),
                ("files_found", models.PositiveIntegerField(default=0)),
                ("imported_questions", models.PositiveIntegerField(default=0)),
                ("duplicate_questions", models.PositiveIntegerField(default=0)),
                ("skipped_questions", models.PositiveIntegerField(default=0)),
                ("errors", models.JSONField(blank=True, default=list)),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="Subject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160, unique=True)),
                ("slug", models.SlugField(max_length=180, unique=True)),
                ("source_path", models.CharField(blank=True, max_length=500)),
                ("imported_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="DailyActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField()),
                ("total_answers", models.PositiveIntegerField(default=0)),
                ("correct_answers", models.PositiveIntegerField(default=0)),
                ("wrong_answers", models.PositiveIntegerField(default=0)),
                ("points", models.IntegerField(default=0)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="daily_activity", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["day"]},
        ),
        migrations.CreateModel(
            name="Question",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField()),
                ("source_file", models.CharField(max_length=500)),
                ("hash", models.CharField(db_index=True, max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="exams.subject")),
            ],
            options={
                "ordering": ["id"],
                "indexes": [
                    models.Index(fields=["subject", "hash"], name="exams_quest_subject_10e9e4_idx"),
                    models.Index(fields=["subject", "created_at"], name="exams_quest_subject_73eb7d_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="UserSubjectStats",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_answered", models.PositiveIntegerField(default=0)),
                ("unique_questions_seen", models.PositiveIntegerField(default=0)),
                ("correct_answers", models.PositiveIntegerField(default=0)),
                ("wrong_answers", models.PositiveIntegerField(default=0)),
                ("points", models.IntegerField(default=0)),
                ("last_activity_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_stats", to="exams.subject")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subject_stats", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "subject"], name="exams_users_user_id_1649d4_idx"),
                    models.Index(fields=["subject", "-points"], name="exams_users_subject_698233_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AnswerVariant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField()),
                ("is_correct", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(default=0)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="variants", to="exams.question")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="TestSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("random", "Random weighted"), ("new", "Only new questions"), ("mistakes", "Work on mistakes"), ("hard", "Hard questions"), ("rare", "Rarely seen questions"), ("review_all", "Review all"), ("spaced", "Spaced repetition")], default="random", max_length=32)),
                ("total_questions", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("active", "Active"), ("finished", "Finished")], default="active", max_length=16)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("score", models.IntegerField(default=0)),
                ("correct_count", models.PositiveIntegerField(default=0)),
                ("wrong_count", models.PositiveIntegerField(default=0)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="test_sessions", to="exams.subject")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="test_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(fields=["user", "status"], name="exams_tests_user_id_dab2ab_idx"),
                    models.Index(fields=["subject", "started_at"], name="exams_tests_subject_17952d_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="TestSessionQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField()),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="session_entries", to="exams.question")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="session_questions", to="exams.testsession")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="TestAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_correct", models.BooleanField(default=False)),
                ("answered_at", models.DateTimeField(auto_now_add=True)),
                ("time_spent", models.PositiveIntegerField(default=0)),
                ("points_awarded", models.IntegerField(default=0)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="test_answers", to="exams.question")),
                ("selected_variant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="selected_answers", to="exams.answervariant")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="answers", to="exams.testsession")),
            ],
            options={
                "ordering": ["answered_at"],
                "indexes": [
                    models.Index(fields=["session", "question"], name="exams_testa_session_479c6a_idx"),
                    models.Index(fields=["question", "is_correct"], name="exams_testa_question_84bdc5_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="UserQuestionProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("times_seen", models.PositiveIntegerField(default=0)),
                ("times_correct", models.PositiveIntegerField(default=0)),
                ("times_wrong", models.PositiveIntegerField(default=0)),
                ("current_streak", models.IntegerField(default=0)),
                ("best_streak", models.PositiveIntegerField(default=0)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("last_correct_at", models.DateTimeField(blank=True, null=True)),
                ("last_wrong_at", models.DateTimeField(blank=True, null=True)),
                ("is_mastered", models.BooleanField(default=False)),
                ("personal_weight", models.FloatField(default=1.0)),
                ("points_earned", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="progress_records", to="exams.question")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="question_progress", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "question"], name="exams_userq_user_id_70ce09_idx"),
                    models.Index(fields=["user", "is_mastered"], name="exams_userq_user_id_15a0a5_idx"),
                    models.Index(fields=["user", "times_wrong"], name="exams_userq_user_id_7d32c4_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="dailyactivity",
            constraint=models.UniqueConstraint(fields=("user", "day"), name="unique_daily_activity"),
        ),
        migrations.AddConstraint(
            model_name="usersubjectstats",
            constraint=models.UniqueConstraint(fields=("user", "subject"), name="unique_user_subject_stats"),
        ),
        migrations.AddConstraint(
            model_name="answervariant",
            constraint=models.UniqueConstraint(fields=("question", "text"), name="unique_variant_text_per_question"),
        ),
        migrations.AddConstraint(
            model_name="testsessionquestion",
            constraint=models.UniqueConstraint(fields=("session", "question"), name="unique_question_per_session"),
        ),
        migrations.AddConstraint(
            model_name="testsessionquestion",
            constraint=models.UniqueConstraint(fields=("session", "order"), name="unique_order_per_session"),
        ),
        migrations.AddConstraint(
            model_name="testanswer",
            constraint=models.UniqueConstraint(fields=("session", "question"), name="unique_answer_per_question_session"),
        ),
        migrations.AddConstraint(
            model_name="userquestionprogress",
            constraint=models.UniqueConstraint(fields=("user", "question"), name="unique_user_question_progress"),
        ),
    ]
