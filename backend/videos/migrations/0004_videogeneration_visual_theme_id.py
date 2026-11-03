from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("videos", "0003_videogeneration_template_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="videogeneration",
            name="visual_theme_id",
            field=models.CharField(
                choices=[
                    ("cinematic_stories", "Cinematic Stories"),
                    ("kinetic_editorial", "Kinetic Editorial"),
                    ("modern_product", "Modern Product"),
                ],
                default="cinematic_stories",
                max_length=32,
            ),
        ),
    ]
