"""
Tokens per turn for one thread, to show that a turn's cost doesn't grow with the chat.

    python manage.py token_report              # the most recently used thread
    python manage.py token_report <thread-id>
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from api.models import Thread


class Command(BaseCommand):
    help = "Print LLM tokens per turn for a thread."

    def add_arguments(self, parser):
        parser.add_argument("thread", nargs="?")

    def handle(self, *args, thread=None, **options):
        t = Thread.objects.filter(pk=thread).first() if thread else Thread.objects.order_by("-updated_at").first()
        if t is None:
            raise CommandError("No such thread.")
        self.stdout.write(f"thread {t.id}: {t.title}\n")
        self.stdout.write(f"{'turn':>4}  {'route':<10} {'prompt':>7} {'output':>7} {'total':>7}  calls")
        for i, m in enumerate(t.messages.all(), start=1):
            prompt = sum(u["prompt_tokens"] for u in m.usage)
            output = sum(u["completion_tokens"] for u in m.usage)
            per_call = defaultdict(int)
            for u in m.usage:
                per_call[u["purpose"]] += u["total_tokens"]
            calls = ", ".join(f"{k} {v}" for k, v in per_call.items())
            self.stdout.write(f"{i:>4}  {m.route:<10} {prompt:>7} {output:>7} {m.total_tokens:>7}  {calls}")
