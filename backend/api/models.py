"""
App records, kept in Postgres' `public` schema. The uploaded data itself lives in a separate
schema per dataset (ds_1, ds_2, ...); these tables only describe it and hold the chats.
"""

import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class Dataset(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        LOADING = "loading"          # reading sheets and copying rows into Postgres
        DESCRIBING = "describing"    # LLM column descriptions
        READY = "ready"
        FAILED = "failed"

    name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(default=0)
    schema_name = models.CharField(max_length=63, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    progress = models.JSONField(default=dict, encoder=DjangoJSONEncoder)        # {"sheet", "rows", "total"}
    error = models.TextField(blank=True)
    report = models.JSONField(default=list, encoder=DjangoJSONEncoder)          # per-sheet ingest summary
    catalog = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    timings = models.JSONField(default=dict)
    is_sample = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class GlossaryEntry(models.Model):
    """'revenue means net_amount': a user's definition that applies to later questions on this dataset."""
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="glossary")
    term = models.CharField(max_length=100)
    meaning = models.TextField()
    columns = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "term"], name="one_meaning_per_term")]


class Thread(models.Model):
    """One conversation. Its id is also LangGraph's thread_id, so the checkpointer keys on it."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="threads")
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class Message(models.Model):
    """One question and its answer: the full transcript the user sees, and the per-turn token log.
    (The agent itself only remembers the last few turns, through the checkpointer.)"""
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    question = models.TextField()
    blocks = models.JSONField(default=list, encoder=DjangoJSONEncoder)
    route = models.CharField(max_length=20, blank=True)
    sql = models.TextField(blank=True)
    usage = models.JSONField(default=list)
    total_tokens = models.IntegerField(default=0)
    seconds = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
