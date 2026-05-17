from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="answervariant",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_correct=True),
                fields=("question",),
                name="unique_correct_variant_per_question",
            ),
        ),
    ]
