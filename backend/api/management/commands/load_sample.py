"""
Generate the sample workbook and load it as a ready-to-use dataset, so there is something
to chat with straight after setup.

    python manage.py load_sample            # ~100k rows, about a minute including descriptions
    python manage.py load_sample --full     # ~1M rows, a few minutes
"""

import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from api import jobs
from api.models import Dataset


class Command(BaseCommand):
    help = "Generate the sample workbook and load it as a dataset."

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="the full ~1M-row workbook instead of ~100k rows")

    def handle(self, *args, full, **options):
        scale = 1.0 if full else 0.1
        out = settings.REPO_DIR / "data" / f"sample_{'1m' if full else '100k'}.xlsx"
        if not out.exists():
            self.stdout.write(f"Generating {out.name} ...")
            subprocess.run([sys.executable, str(settings.REPO_DIR / "scripts" / "generate_workbook.py"),
                            "--scale", str(scale), "--out", str(out)], check=True)

        name = f"Sample retailer, FY25-FY26 ({'1M' if full else '100k'} rows)"
        ds = Dataset.objects.create(name=name, file_path=str(out), file_size=out.stat().st_size, is_sample=True)
        self.stdout.write(f"Loading dataset {ds.pk} ...")
        jobs.run(ds.pk)                      # in this process, not a background thread
        ds.refresh_from_db()
        if ds.status != Dataset.Status.READY:
            self.stderr.write(f"Failed: {ds.error}")
            sys.exit(1)
        rows = sum(t["row_count"] for t in ds.catalog["tables"])
        self.stdout.write(self.style.SUCCESS(
            f"Dataset {ds.pk} ready in schema {ds.schema_name}: {len(ds.catalog['tables'])} tables, {rows:,} rows "
            f"(load {ds.timings.get('load_seconds')}s, descriptions {ds.timings.get('describe_seconds')}s)"))
