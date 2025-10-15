"""Command-line interface for database management."""

import click
import logging
from typing import Optional

from .connection import DatabaseManager, init_database
from .migrations import run_migrations, rollback_migrations, check_migration_status

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.group()
@click.option('--database-url', help='Database connection URL')
@click.pass_context
def cli(ctx, database_url: Optional[str]):
    """Smart Bug Triage Database Management CLI."""
    ctx.ensure_object(dict)
    ctx.obj['database_url'] = database_url


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize the database and create all tables."""
    try:
        database_url = ctx.obj.get('database_url')
        init_database(database_url)
        click.echo("✅ Database initialized successfully!")
    except Exception as e:
        click.echo(f"❌ Failed to initialize database: {e}")
        raise click.Abort()


@cli.command()
@click.pass_context
def migrate(ctx):
    """Run all pending database migrations."""
    try:
        database_url = ctx.obj.get('database_url')
        db_manager = DatabaseManager(database_url)
        db_manager.initialize()
        
        run_migrations(db_manager)
        click.echo("✅ Migrations completed successfully!")
    except Exception as e:
        click.echo(f"❌ Migration failed: {e}")
        raise click.Abort()


@cli.command()
@click.option('--target', help='Target migration version to rollback to')
@click.pass_context
def rollback(ctx, target: Optional[str]):
    """Rollback database migrations."""
    try:
        database_url = ctx.obj.get('database_url')
        db_manager = DatabaseManager(database_url)
        db_manager.initialize()
        
        rollback_migrations(db_manager, target)
        click.echo("✅ Rollback completed successfully!")
    except Exception as e:
        click.echo(f"❌ Rollback failed: {e}")
        raise click.Abort()


@cli.command()
@click.pass_context
def status(ctx):
    """Check database migration status."""
    try:
        database_url = ctx.obj.get('database_url')
        db_manager = DatabaseManager(database_url)
        db_manager.initialize()
        
        status_info = check_migration_status(db_manager)
        
        click.echo("📊 Database Migration Status:")
        click.echo(f"   Total migrations: {status_info['total_migrations']}")
        click.echo(f"   Applied: {len(status_info['applied_migrations'])}")
        click.echo(f"   Pending: {len(status_info['pending_migrations'])}")
        click.echo(f"   Up to date: {'✅' if status_info['up_to_date'] else '❌'}")
        
        if status_info['applied_migrations']:
            click.echo("\n📋 Applied migrations:")
            for migration in status_info['applied_migrations']:
                click.echo(f"   ✅ {migration}")
        
        if status_info['pending_migrations']:
            click.echo("\n⏳ Pending migrations:")
            for migration in status_info['pending_migrations']:
                click.echo(f"   ⏳ {migration}")
                
    except Exception as e:
        click.echo(f"❌ Failed to check status: {e}")
        raise click.Abort()


@cli.command()
@click.pass_context
def health(ctx):
    """Check database connection health."""
    try:
        database_url = ctx.obj.get('database_url')
        db_manager = DatabaseManager(database_url)
        db_manager.initialize()
        
        if db_manager.health_check():
            click.echo("✅ Database connection is healthy!")
        else:
            click.echo("❌ Database connection failed!")
            raise click.Abort()
            
    except Exception as e:
        click.echo(f"❌ Health check failed: {e}")
        raise click.Abort()


@cli.command()
@click.confirmation_option(prompt='Are you sure you want to drop all tables?')
@click.pass_context
def reset(ctx):
    """Drop all database tables (DANGEROUS!)."""
    try:
        database_url = ctx.obj.get('database_url')
        db_manager = DatabaseManager(database_url)
        db_manager.initialize()
        
        db_manager.drop_tables()
        click.echo("✅ All tables dropped successfully!")
        
        # Optionally recreate tables
        if click.confirm('Do you want to recreate the tables?'):
            db_manager.create_tables()
            run_migrations(db_manager)
            click.echo("✅ Tables recreated and migrations applied!")
            
    except Exception as e:
        click.echo(f"❌ Reset failed: {e}")
        raise click.Abort()


if __name__ == '__main__':
    cli()