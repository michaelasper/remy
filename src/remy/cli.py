"""Command-line interface for Remy."""

from __future__ import annotations

import json
import time
from typing import Optional

import typer

from remy.config import get_settings
from remy.db.receipts import offload_receipt_content
from remy.models.context import PlanningContext
from remy.ocr import ReceiptOcrService, ReceiptOcrWorker
from remy.planner.app.planner import generate_plan

app = typer.Typer(help="Remy dinner-planning automation commands.")


@app.command()
def plan(
    context_path: str,
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print output JSON."),
) -> None:
    """
    Generate dinner plan candidates for the provided planning context JSON file.
    """
    with open(context_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    context = PlanningContext.model_validate(payload)
    plan = generate_plan(context)
    as_dict = plan.model_dump()

    if pretty:
        typer.echo(json.dumps(as_dict, indent=2, sort_keys=True))
    else:
        typer.echo(json.dumps(as_dict))


@app.command("receipt-ocr")
def receipt_ocr(
    receipt_id: int = typer.Argument(..., help="Receipt ID to process."),
    lang: str = typer.Option("eng", "--lang", help="Tesseract language code to use."),
    pretty: bool = typer.Option(True, "--pretty/--no-pretty", help="Pretty-print OCR JSON."),
) -> None:
    """
    Run OCR against a previously uploaded receipt and display the stored result.
    """

    settings = get_settings()
    service = ReceiptOcrService(lang=lang)
    result = service.process_receipt(receipt_id)
    payload = result.model_dump(mode="json")
    output = json.dumps(payload, indent=2 if pretty else None, sort_keys=pretty)
    typer.echo(output)
    if result.status == "succeeded":
        try:
            offload_receipt_content(receipt_id, archive_dir=settings.ocr_archive_path)
        except Exception as exc:  # pragma: no cover - CLI warning
            typer.secho(f"Warning: unable to archive receipt: {exc}", fg=typer.colors.YELLOW)


@app.command("ocr-worker")
def ocr_worker(
    once: bool = typer.Option(False, "--once", help="Process a single batch then exit."),
    poll_interval: Optional[float] = typer.Option(
        None,
        "--poll-interval",
        help="Override poll interval (seconds).",
    ),
    batch_size: Optional[int] = typer.Option(None, "--batch-size", help="Override batch size."),
) -> None:
    """Run the background OCR worker loop from the CLI."""

    settings = get_settings()
    worker = ReceiptOcrWorker(
        poll_interval=poll_interval or settings.ocr_worker_poll_interval,
        batch_size=batch_size or settings.ocr_worker_batch_size,
        service=ReceiptOcrService(lang=settings.ocr_default_lang),
        archive_dir=settings.ocr_archive_path,
    )

    if once:
        processed = worker.poll_once()
        typer.echo(f"Processed {processed} receipt(s).")
        return

    typer.echo("Starting OCR worker. Press Ctrl+C to stop.")
    worker.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        typer.echo("Stopping worker…")
        worker.stop()


def main(argv: Optional[list[str]] = None) -> None:
    """Entry point for `python -m remy`."""
    app(prog_name="remy", args=argv)


if __name__ == "__main__":
    main()
