from django.core.management.base import BaseCommand
from django.urls import get_resolver


class Command(BaseCommand):
    help = "List all registered URL patterns."

    def handle(self, *args, **options):
        def walk(patterns, prefix=""):
            for p in patterns:
                if hasattr(p, "url_patterns"):
                    walk(p.url_patterns, prefix + str(p.pattern))
                else:
                    self.stdout.write(prefix + str(p.pattern))

        walk(get_resolver().url_patterns)
