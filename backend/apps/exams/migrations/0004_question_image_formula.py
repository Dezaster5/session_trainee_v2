from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0003_topics_live_coding"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="formula",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="question",
            name="image",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
