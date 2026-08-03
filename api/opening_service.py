"""Vercel Python Function entrypoint for the hosted opening read boundary."""

from bughouse_explorer.opening.vercel_hosted import create_vercel_app


app = create_vercel_app()
