import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exams", "0002_answer_variant_correct_constraint"),
    ]

    operations = [
        migrations.CreateModel(
            name="Topic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=220)),
                ("slug", models.SlugField(max_length=240)),
                ("type", models.CharField(choices=[("theory", "Theory"), ("live_coding", "Live coding")], default="theory", max_length=32)),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="topics", to="exams.subject")),
            ],
            options={
                "ordering": ["subject__name", "type", "order", "title"],
                "indexes": [models.Index(fields=["subject", "type", "order"], name="exams_topic_subject_aa1b2c_idx")],
                "constraints": [models.UniqueConstraint(fields=("subject", "slug", "type"), name="unique_topic_slug_type_per_subject")],
            },
        ),
        migrations.AddField(
            model_name="question",
            name="difficulty",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="explanation",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="import_format",
            field=models.CharField(choices=[("pdf", "PDF"), ("json", "JSON")], default="pdf", max_length=32),
        ),
        migrations.AddField(
            model_name="question",
            name="topic",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="questions", to="exams.topic"),
        ),
        migrations.AddIndex(
            model_name="question",
            index=models.Index(fields=["subject", "topic"], name="exams_quest_subject_81f9cc_idx"),
        ),
        migrations.AddField(
            model_name="usersubjectstats",
            name="live_coding_attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="usersubjectstats",
            name="live_coding_solved",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="usersubjectstats",
            name="average_live_coding_similarity",
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name="importrun",
            name="imported_live_coding_tasks",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importrun",
            name="duplicate_live_coding_tasks",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importrun",
            name="skipped_live_coding_tasks",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="LiveCodingTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=260)),
                ("prompt", models.TextField()),
                ("language", models.CharField(max_length=80)),
                ("expected_solution", models.TextField()),
                ("check_type", models.CharField(default="similarity", max_length=64)),
                ("difficulty", models.CharField(blank=True, max_length=80, null=True)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("source_file", models.CharField(max_length=500)),
                ("hash", models.CharField(db_index=True, max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="live_coding_tasks", to="exams.subject")),
                ("topic", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="live_coding_tasks", to="exams.topic")),
            ],
            options={
                "ordering": ["id"],
                "indexes": [
                    models.Index(fields=["subject", "topic"], name="exams_live_subject_3f2a5d_idx"),
                    models.Index(fields=["language"], name="exams_live_language_3a0ac7_idx"),
                    models.Index(fields=["difficulty"], name="exams_live_difficu_38e9a9_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="LiveCodingSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("random", "Random weighted"), ("new", "Only new tasks"), ("mistakes", "Weak tasks"), ("hard", "Hard tasks"), ("rare", "Rarely attempted tasks"), ("review_all", "Review all"), ("spaced", "Spaced repetition")], default="random", max_length=32)),
                ("total_tasks", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("active", "Active"), ("finished", "Finished")], default="active", max_length=16)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("score", models.IntegerField(default=0)),
                ("average_similarity", models.FloatField(default=0)),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="live_coding_sessions", to="exams.subject")),
                ("topic", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="live_coding_sessions", to="exams.topic")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="live_coding_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(fields=["user", "status"], name="exams_live_user_id_4a9b3d_idx"),
                    models.Index(fields=["subject", "started_at"], name="exams_live_subject_d02db2_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="UserLiveCodingProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("attempts_count", models.PositiveIntegerField(default=0)),
                ("best_similarity", models.FloatField(default=0)),
                ("last_similarity", models.FloatField(default=0)),
                ("is_solved", models.BooleanField(default=False)),
                ("last_submitted_code", models.TextField(blank=True)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("first_solved_at", models.DateTimeField(blank=True, null=True)),
                ("points_earned", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="progress_records", to="exams.livecodingtask")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="live_coding_progress", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "task"], name="exams_userl_user_id_711cf8_idx"),
                    models.Index(fields=["user", "is_solved"], name="exams_userl_user_id_53408d_idx"),
                    models.Index(fields=["user", "best_similarity"], name="exams_userl_user_id_8b6fd5_idx"),
                ],
                "constraints": [models.UniqueConstraint(fields=("user", "task"), name="unique_user_live_coding_progress")],
            },
        ),
        migrations.CreateModel(
            name="LiveCodingSessionTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField()),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="session_tasks", to="exams.livecodingsession")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="session_entries", to="exams.livecodingtask")),
            ],
            options={
                "ordering": ["order", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("session", "task"), name="unique_task_per_live_coding_session"),
                    models.UniqueConstraint(fields=("session", "order"), name="unique_live_coding_order_per_session"),
                ],
            },
        ),
        migrations.CreateModel(
            name="LiveCodingAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("submitted_code", models.TextField()),
                ("similarity_score", models.FloatField(default=0)),
                ("status", models.CharField(choices=[("excellent", "Excellent"), ("good", "Good"), ("needs_practice", "Needs practice"), ("wrong", "Wrong")], default="wrong", max_length=32)),
                ("points_awarded", models.IntegerField(default=0)),
                ("feedback", models.TextField(blank=True)),
                ("attempted_at", models.DateTimeField(auto_now_add=True)),
                ("time_spent", models.PositiveIntegerField(default=0)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="exams.livecodingsession")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="exams.livecodingtask")),
            ],
            options={
                "ordering": ["attempted_at"],
                "indexes": [
                    models.Index(fields=["session", "task"], name="exams_live_session_97779f_idx"),
                    models.Index(fields=["task", "status"], name="exams_live_task_id_81c43c_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("session", "task"), name="unique_live_coding_attempt_per_task_session"),
                ],
            },
        ),
    ]
