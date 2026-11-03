from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("videos", "0006_mediaasset_attribution_url_mediaasset_photographer_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediaasset",
            name="generation_prompt",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="generation_seed",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
    ]
