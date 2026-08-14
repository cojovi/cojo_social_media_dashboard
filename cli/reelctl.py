#!/usr/bin/env python3
import sys
import os
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional


# Setup import path for backend app
backend_dir = Path(__file__).resolve().parents[1] / "backend"
sys.path.append(str(backend_dir))

# Try to import typer and rich, else define clean fallbacks
try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich import print as rprint
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    class TyperDummy:
        def run(self): pass
    typer = TyperDummy()

# Import backend modules
try:
    from app import models, scanner, settings, database
    from app.gemini_service import analyze_video_with_gemini, GeminiServiceError
    # Pre-flight DB check
    database.init_db()
except ImportError as e:
    print(f"Error importing ReelVault backend modules: {e}")
    print("Ensure the script is run from the project root or sys.path is correct.")
    sys.exit(1)

# Initialize Typer and Console
if HAS_RICH:
    app = typer.Typer(help="🚀 ReelVault CLI - Organize reels & prewrite captions with Gemini")
    console = Console()
    err_console = Console(stderr=True)
else:
    # Typer not available
    print("Typer and Rich are required to run this CLI. Please run 'pip install typer rich'")
    sys.exit(1)

@app.command(name="scan")
def scan_folder():
    """
    Scan the configured reels folder and add new videos to the database.
    """
    console.print(f"[bold cyan]Scanning folder:[/bold cyan] {settings.settings.REELS_FOLDER}...")
    try:
        stats = scanner.scan_reels_folder()
        console.print(Panel(
            f"🎉 [bold green]Scan completed successfully![/bold green]\n\n"
            f"📁 [bold]Scanned files:[/bold] {stats['scanned']}\n"
            f"➕ [bold]Newly added reels:[/bold] {stats['added']}\n"
            f"🔄 [bold]Updated metadata:[/bold] {stats['updated']}",
            title="Scan Summary",
            border_style="green"
        ))
    except Exception as e:
        err_console.print(f"[bold red]Scan failed:[/bold red] {e}")
        sys.exit(1)

@app.command(name="list")
def list_reels():
    """
    List all reels in the database with status, approval, and final post info.
    """
    try:
        reels = models.get_all_reels()
        if not reels:
            console.print("[yellow]No reels indexed yet. Run 'reelctl scan' first.[/yellow]")
            return
            
        table = Table(title="Reels Archive", border_style="magenta")
        table.add_column("ID", justify="right", style="cyan", no_wrap=True)
        table.add_column("Filename", style="white")
        table.add_column("Duration", justify="right", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Approved", justify="center")
        table.add_column("Final Post", justify="center")
        
        for r in reels:
            app_str = "✅ YES" if r["approved"] else "❌ NO"
            post_str = "📝 YES" if (r["final_post_text"] and r["final_post_text"].strip()) else "⬜ NO"
            
            # Format status color
            status_color = "white"
            if r["status"] == "ready": status_color = "bold green"
            elif r["status"] == "draft": status_color = "dim white"
            elif r["status"] == "needs_review": status_color = "bold yellow"
            elif r["status"] == "posted": status_color = "blue"
            
            table.add_row(
                str(r["id"]),
                r["filename"],
                f"{r['duration_seconds']:.1f}s",
                f"[{status_color}]{r['status']}[/{status_color}]",
                app_str,
                post_str
            )
            
        console.print(table)
    except Exception as e:
        err_console.print(f"[bold red]Failed to list reels:[/bold red] {e}")
        sys.exit(1)

@app.command(name="show")
def show_reel(reel_id: int = typer.Argument(..., help="The database ID of the reel")):
    """
    Show all information for a specific reel.
    """
    try:
        r = models.get_reel_by_id(reel_id)
        if not r:
            err_console.print(f"[bold red]Error:[/bold red] Reel with ID {reel_id} not found.")
            sys.exit(1)
            
        console.print(Panel(
            f"[bold cyan]ID:[/bold cyan] {r['id']}\n"
            f"[bold cyan]Filename:[/bold cyan] {r['filename']}\n"
            f"[bold cyan]Path:[/bold cyan] {r['filepath']}\n"
            f"[bold cyan]Size:[/bold cyan] {r['file_size'] / (1024*1024):.2f} MB\n"
            f"[bold cyan]Duration:[/bold cyan] {r['duration_seconds']:.1f} seconds\n"
            f"[bold cyan]Thumbnail:[/bold cyan] {r['thumbnail_path'] or 'None'}\n"
            f"[bold cyan]Discovered:[/bold cyan] {r['discovered_at']}\n"
            f"[bold cyan]Status:[/bold cyan] [bold yellow]{r['status']}[/bold yellow] | [bold cyan]Approved:[/bold cyan] {'✅ YES' if r['approved'] else '❌ NO'}\n"
            f"[bold cyan]Hashtags:[/bold cyan] {r['hashtags'] or 'None'}\n"
            f"[bold cyan]Notes:[/bold cyan] {r['notes'] or 'None'}",
            title=f"🎬 Reel Metadata: {r['filename']}",
            border_style="cyan"
        ))
        
        # Display Captions
        console.print("\n[bold magenta]Manual Post Caption:[/bold magenta]")
        console.print(r['manual_post_text'] or "[italic dim]Empty[/italic dim]")
        
        console.print("\n[bold green]Final Post Caption (Ready for Poster Agent):[/bold green]")
        console.print(r['final_post_text'] or "[italic dim]Empty[/italic dim]")
        
        if r['ai_summary']:
            console.print(Panel(
                f"[bold cyan]AI Summary:[/bold cyan]\n{r['ai_summary']}\n\n"
                f"[bold cyan]AI Suggested Caption:[/bold cyan]\n{r['ai_suggested_post_text']}\n\n"
                f"[bold cyan]AI Suggested Hashtags:[/bold cyan] {r['ai_suggested_hashtags']}\n"
                f"[bold cyan]Category:[/bold cyan] {r['ai_category']} | [bold cyan]Best Platform:[/bold cyan] {r['ai_platform_suggestion']}\n"
                f"[bold cyan]Last Analyzed:[/bold cyan] {r['ai_last_analyzed_at']}",
                title="✨ Gemini AI Analysis",
                border_style="magenta"
            ))
            
    except Exception as e:
        err_console.print(f"[bold red]Failed to fetch reel detail:[/bold red] {e}")
        sys.exit(1)

@app.command(name="set-post")
def set_post(
    reel_id: int = typer.Argument(..., help="The database ID of the reel"),
    text: str = typer.Argument(..., help="The caption/post text to save")
):
    """
    Update the final post caption text for a reel (defaults to final_post_text).
    """
    try:
        r = models.get_reel_by_id(reel_id)
        if not r:
            err_console.print(f"[bold red]Error:[/bold red] Reel with ID {reel_id} not found.")
            sys.exit(1)
            
        success = models.update_reel(reel_id, {"final_post_text": text})
        if success:
            console.print(f"[bold green]Success:[/bold green] Updated final caption for reel {reel_id}.")
        else:
            err_console.print("[bold red]Failed to save post caption.[/bold red]")
            sys.exit(1)
    except Exception as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

@app.command(name="set-hashtags")
def set_hashtags(
    reel_id: int = typer.Argument(..., help="The database ID of the reel"),
    tags: str = typer.Argument(..., help="Space or comma separated hashtags")
):
    """
    Update manual hashtags for a reel.
    """
    try:
        r = models.get_reel_by_id(reel_id)
        if not r:
            err_console.print(f"[bold red]Error:[/bold red] Reel with ID {reel_id} not found.")
            sys.exit(1)
            
        success = models.update_reel(reel_id, {"hashtags": tags})
        if success:
            console.print(f"[bold green]Success:[/bold green] Updated hashtags for reel {reel_id}.")
        else:
            err_console.print("[bold red]Failed to save hashtags.[/bold red]")
            sys.exit(1)
    except Exception as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

@app.command(name="approve")
def approve_reel(reel_id: int = typer.Argument(..., help="The database ID of the reel")):
    """
    Mark a reel as approved (approved = true).
    """
    try:
        r = models.get_reel_by_id(reel_id)
        if not r:
            err_console.print(f"[bold red]Error:[/bold red] Reel with ID {reel_id} not found.")
            sys.exit(1)
            
        success = models.update_reel(reel_id, {"approved": True})
        if success:
            console.print(f"[bold green]Success:[/bold green] Reel {reel_id} marked as APPROVED.")
        else:
            err_console.print("[bold red]Failed to update approval.[/bold red]")
            sys.exit(1)
    except Exception as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

@app.command(name="status")
def set_status(
    reel_id: int = typer.Argument(..., help="The database ID of the reel"),
    status: str = typer.Argument(..., help="Status value: draft, needs_review, ready, posted, archived")
):
    """
    Update the status of a reel. If setting to 'ready', requires approved=True and valid final caption.
    """
    valid_statuses = {"draft", "needs_review", "ready", "posted", "archived"}
    if status not in valid_statuses:
        err_console.print(f"[bold red]Error:[/bold red] Invalid status. Choose from {', '.join(valid_statuses)}")
        sys.exit(1)
        
    try:
        r = models.get_reel_by_id(reel_id)
        if not r:
            err_console.print(f"[bold red]Error:[/bold red] Reel with ID {reel_id} not found.")
            sys.exit(1)
            
        # Ready queue safety rule validation
        if status == "ready":
            final_post = r.get("final_post_text") or ""
            if not final_post.strip():
                err_console.print("[bold red]Validation Error:[/bold red] Cannot mark reel as ready without final post caption.")
                sys.exit(1)
            # Auto-approve if setting status ready
            success = models.update_reel(reel_id, {"status": status, "approved": True})
        elif status == "posted":
            success = models.update_reel(reel_id, {"status": status, "posted_at": datetime.now().isoformat()})
        elif status == "archived":
            success = models.update_reel(reel_id, {"status": status, "archived_at": datetime.now().isoformat()})
        else:
            success = models.update_reel(reel_id, {"status": status})
            
        if success:
            console.print(f"[bold green]Success:[/bold green] Reel {reel_id} status updated to '{status}'.")
        else:
            err_console.print("[bold red]Failed to save status updates.[/bold red]")
            sys.exit(1)
            
    except Exception as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

@app.command(name="analyze")
def analyze_reel(reel_id: int = typer.Argument(..., help="The database ID of the reel")):
    """
    Trigger Gemini API video analysis, copywriting, and category classification.
    """
    try:
        r = models.get_reel_by_id(reel_id)
        if not r:
            err_console.print(f"[bold red]Error:[/bold red] Reel with ID {reel_id} not found.")
            sys.exit(1)
            
        console.print(f"[bold magenta]Starting Gemini Video Analysis for reel {reel_id}...[/bold magenta]")
        console.print("[dim]This uploads the local file temporary and processes it. Please wait...[/dim]")
        
        analysis = analyze_video_with_gemini(r["filepath"])
        
        # Save analysis
        tags_list = analysis.get("hashtags", [])
        tags_str = " ".join(tags_list) if isinstance(tags_list, list) else str(tags_list)
        
        update_data = {
            "ai_summary": analysis.get("summary", ""),
            "ai_suggested_post_text": analysis.get("suggested_post", ""),
            "ai_suggested_hashtags": tags_str,
            "ai_category": analysis.get("category", "Showcase"),
            "ai_platform_suggestion": analysis.get("platform_suggestion", "Instagram"),
            "ai_last_analyzed_at": datetime.now().isoformat()
        }
        
        models.update_reel(reel_id, update_data)
        
        console.print(Panel(
            f"🎬 [bold green]AI Analysis Complete for {r['filename']}[/bold green]\n\n"
            f"[bold cyan]AI Summary:[/bold cyan]\n{analysis.get('summary')}\n\n"
            f"[bold cyan]AI Caption:[/bold cyan]\n{analysis.get('suggested_post')}\n\n"
            f"[bold cyan]AI Hashtags:[/bold cyan] {tags_str}\n"
            f"[bold cyan]Category:[/bold cyan] {analysis.get('category')} | [bold cyan]Platform:[/bold cyan] {analysis.get('platform_suggestion')}",
            title="Analysis Output",
            border_style="green"
        ))
        
    except GeminiServiceError as e:
        err_console.print(f"[bold red]AI Service Warning:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        err_console.print(f"[bold red]Error occurred during analysis:[/bold red] {e}")
        sys.exit(1)

@app.command(name="next-ready")
def next_ready():
    """
    Get the next ready-to-post reel (approved, ready, has final caption).
    Useful for autonomous poster agents.
    """
    try:
        queue = models.get_ready_queue()
        if not queue:
            console.print("[yellow]No reels in the Ready Queue currently.[/yellow]")
            return
            
        next_reel = queue[0]
        # Return simple output suitable for parsing by command execution agents
        console.print(Panel(
            f"[bold cyan]ID:[/bold cyan] {next_reel['id']}\n"
            f"[bold cyan]Filename:[/bold cyan] {next_reel['filename']}\n"
            f"[bold cyan]Filepath:[/bold cyan] {next_reel['filepath']}\n"
            f"[bold green]Final Caption:[/bold green]\n{next_reel['final_post_text']}\n\n"
            f"[bold green]Hashtags:[/bold green] {next_reel['hashtags'] or ''}",
            title="🎯 Next Approved Reel Ready to Post",
            border_style="green"
        ))
    except Exception as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

@app.command(name="export-ready")
def export_ready(
    format_type: str = typer.Option("json", "--format", "-f", help="Export format: json or csv"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Optional output filepath. Else prints to stdout.")
):
    """
    Export all reels in the Ready Queue to JSON or CSV format.
    """
    if format_type.lower() not in {"json", "csv"}:
        err_console.print("[bold red]Error:[/bold red] Format must be 'json' or 'csv'.")
        sys.exit(1)
        
    try:
        queue = models.get_ready_queue()
        
        # Serialize
        if format_type.lower() == "json":
            output_data = json.dumps(queue, indent=2)
        else:
            # CSV export
            import io
            f = io.StringIO()
            writer = csv.writer(f)
            if queue:
                # Write header
                writer.writerow(queue[0].keys())
                for r in queue:
                    writer.writerow(r.values())
            output_data = f.getvalue()
            
        # Handle Output
        if output_file:
            out_path = Path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output_data)
            console.print(f"[bold green]Exported {len(queue)} ready reels successfully to {out_path}[/bold green]")
        else:
            # Output directly to stdout
            print(output_data)
            
    except Exception as e:
        err_console.print(f"[bold red]Failed to export ready queue:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    app()
