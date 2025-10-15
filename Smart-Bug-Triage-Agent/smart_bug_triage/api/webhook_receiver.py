"""Webhook receiver for real-time bug report notifications."""

import hashlib
import hmac
import json
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from dataclasses import dataclass
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn

from ..models.common import BugReport


@dataclass
class WebhookEvent:
    """Webhook event data model."""
    source: str  # github, jira
    event_type: str
    timestamp: datetime
    payload: Dict[str, Any]
    signature: Optional[str] = None


class WebhookReceiver:
    """Webhook receiver for GitHub and Jira notifications."""
    
    def __init__(
        self,
        github_secret: Optional[str] = None,
        jira_secret: Optional[str] = None,
        port: int = 8080,
        host: str = "0.0.0.0"
    ):
        """Initialize webhook receiver.
        
        Args:
            github_secret: GitHub webhook secret for signature verification
            jira_secret: Jira webhook secret for signature verification
            port: Port to listen on
            host: Host to bind to
        """
        self.github_secret = github_secret
        self.jira_secret = jira_secret
        self.port = port
        self.host = host
        self.logger = logging.getLogger(__name__)
        
        # Event handlers
        self.event_handlers: Dict[str, Callable[[WebhookEvent], None]] = {}
        
        # FastAPI app
        self.app = FastAPI(title="Smart Bug Triage Webhook Receiver")
        self._setup_routes()
    
    def register_handler(self, event_type: str, handler: Callable[[WebhookEvent], None]):
        """Register an event handler.
        
        Args:
            event_type: Type of event to handle (e.g., 'github.issues.opened')
            handler: Function to call when event occurs
        """
        self.event_handlers[event_type] = handler
        self.logger.info(f"Registered handler for event type: {event_type}")
    
    def _setup_routes(self):
        """Set up FastAPI routes."""
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
        
        @self.app.post("/webhooks/github")
        async def github_webhook(request: Request, background_tasks: BackgroundTasks):
            """Handle GitHub webhook events."""
            try:
                # Get headers
                event_type = request.headers.get("X-GitHub-Event")
                signature = request.headers.get("X-Hub-Signature-256")
                delivery_id = request.headers.get("X-GitHub-Delivery")
                
                if not event_type:
                    raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")
                
                # Get payload
                payload = await request.body()
                
                # Verify signature if secret is configured
                if self.github_secret and signature:
                    if not self._verify_github_signature(payload, signature):
                        raise HTTPException(status_code=401, detail="Invalid signature")
                
                # Parse JSON payload
                try:
                    json_payload = json.loads(payload.decode())
                except json.JSONDecodeError:
                    raise HTTPException(status_code=400, detail="Invalid JSON payload")
                
                # Create webhook event
                webhook_event = WebhookEvent(
                    source="github",
                    event_type=event_type,
                    timestamp=datetime.utcnow(),
                    payload=json_payload,
                    signature=signature
                )
                
                # Process event in background
                background_tasks.add_task(self._process_event, webhook_event)
                
                self.logger.info(f"Received GitHub webhook: {event_type} (delivery: {delivery_id})")
                
                return JSONResponse(
                    status_code=200,
                    content={"message": "Webhook received", "event_type": event_type}
                )
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error processing GitHub webhook: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
        
        @self.app.post("/webhooks/jira")
        async def jira_webhook(request: Request, background_tasks: BackgroundTasks):
            """Handle Jira webhook events."""
            try:
                # Get headers
                event_type = request.headers.get("X-Atlassian-Webhook-Identifier")
                
                # Get payload
                payload = await request.body()
                
                # Verify signature if secret is configured
                if self.jira_secret:
                    signature = request.headers.get("X-Hub-Signature")
                    if signature and not self._verify_jira_signature(payload, signature):
                        raise HTTPException(status_code=401, detail="Invalid signature")
                
                # Parse JSON payload
                try:
                    json_payload = json.loads(payload.decode())
                except json.JSONDecodeError:
                    raise HTTPException(status_code=400, detail="Invalid JSON payload")
                
                # Extract event type from payload if not in header
                if not event_type:
                    event_type = json_payload.get("webhookEvent", "unknown")
                
                # Create webhook event
                webhook_event = WebhookEvent(
                    source="jira",
                    event_type=event_type,
                    timestamp=datetime.utcnow(),
                    payload=json_payload
                )
                
                # Process event in background
                background_tasks.add_task(self._process_event, webhook_event)
                
                self.logger.info(f"Received Jira webhook: {event_type}")
                
                return JSONResponse(
                    status_code=200,
                    content={"message": "Webhook received", "event_type": event_type}
                )
                
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error processing Jira webhook: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")
    
    def _verify_github_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook signature."""
        if not signature.startswith("sha256="):
            return False
        
        expected_signature = hmac.new(
            self.github_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        received_signature = signature[7:]  # Remove 'sha256=' prefix
        
        return hmac.compare_digest(expected_signature, received_signature)
    
    def _verify_jira_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Jira webhook signature."""
        expected_signature = hmac.new(
            self.jira_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    
    async def _process_event(self, event: WebhookEvent):
        """Process webhook event."""
        try:
            # Determine specific event type
            if event.source == "github":
                specific_event_type = self._get_github_event_type(event)
            elif event.source == "jira":
                specific_event_type = self._get_jira_event_type(event)
            else:
                specific_event_type = f"{event.source}.{event.event_type}"
            
            # Call registered handler
            handler = self.event_handlers.get(specific_event_type)
            if handler:
                try:
                    handler(event)
                    self.logger.info(f"Successfully processed event: {specific_event_type}")
                except Exception as e:
                    self.logger.error(f"Error in event handler for {specific_event_type}: {e}")
            else:
                self.logger.debug(f"No handler registered for event type: {specific_event_type}")
                
        except Exception as e:
            self.logger.error(f"Error processing webhook event: {e}")
    
    def _get_github_event_type(self, event: WebhookEvent) -> str:
        """Get specific GitHub event type."""
        base_type = event.event_type
        
        if base_type == "issues":
            action = event.payload.get("action", "unknown")
            return f"github.issues.{action}"
        elif base_type == "issue_comment":
            action = event.payload.get("action", "unknown")
            return f"github.issue_comment.{action}"
        else:
            return f"github.{base_type}"
    
    def _get_jira_event_type(self, event: WebhookEvent) -> str:
        """Get specific Jira event type."""
        webhook_event = event.payload.get("webhookEvent", "")
        
        if webhook_event.startswith("jira:issue_"):
            return f"jira.{webhook_event.replace('jira:', '')}"
        else:
            return f"jira.{webhook_event}"
    
    def extract_bug_report_from_github(self, event: WebhookEvent) -> Optional[BugReport]:
        """Extract bug report from GitHub webhook event."""
        try:
            if not event.event_type.startswith("issues"):
                return None
            
            issue = event.payload.get("issue", {})
            repository = event.payload.get("repository", {})
            
            # Check if it's actually a bug (has bug label or is in issues)
            labels = [label["name"] for label in issue.get("labels", [])]
            
            bug_report = BugReport(
                id=f"github_{issue['id']}",
                title=issue["title"],
                description=issue.get("body", ""),
                reporter=issue["user"]["login"],
                created_at=datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00")),
                platform="github",
                raw_data={
                    "issue_number": issue["number"],
                    "repository": repository["full_name"],
                    "labels": labels,
                    "html_url": issue["html_url"],
                    "state": issue["state"]
                }
            )
            
            return bug_report
            
        except Exception as e:
            self.logger.error(f"Error extracting bug report from GitHub event: {e}")
            return None
    
    def extract_bug_report_from_jira(self, event: WebhookEvent) -> Optional[BugReport]:
        """Extract bug report from Jira webhook event."""
        try:
            if not event.event_type.endswith("created") and not event.event_type.endswith("updated"):
                return None
            
            issue = event.payload.get("issue", {})
            fields = issue.get("fields", {})
            
            # Check if it's a bug type issue
            issue_type = fields.get("issuetype", {}).get("name", "").lower()
            if "bug" not in issue_type and "defect" not in issue_type:
                return None
            
            bug_report = BugReport(
                id=f"jira_{issue['id']}",
                title=fields["summary"],
                description=fields.get("description", ""),
                reporter=fields.get("reporter", {}).get("displayName", "Unknown"),
                created_at=datetime.fromisoformat(fields["created"].replace("Z", "+00:00")),
                platform="jira",
                raw_data={
                    "key": issue["key"],
                    "project": fields["project"]["key"],
                    "issue_type": fields["issuetype"]["name"],
                    "priority": fields.get("priority", {}).get("name"),
                    "status": fields["status"]["name"],
                    "labels": fields.get("labels", [])
                }
            )
            
            return bug_report
            
        except Exception as e:
            self.logger.error(f"Error extracting bug report from Jira event: {e}")
            return None
    
    def start(self):
        """Start the webhook receiver server."""
        self.logger.info(f"Starting webhook receiver on {self.host}:{self.port}")
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
    
    async def start_async(self):
        """Start the webhook receiver server asynchronously."""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()


# Example usage and event handlers
def create_webhook_receiver_with_handlers(
    github_secret: Optional[str] = None,
    jira_secret: Optional[str] = None,
    bug_processor: Optional[Callable[[BugReport], None]] = None
) -> WebhookReceiver:
    """Create webhook receiver with default event handlers."""
    
    receiver = WebhookReceiver(github_secret, jira_secret)
    
    def handle_github_issue_opened(event: WebhookEvent):
        """Handle GitHub issue opened event."""
        bug_report = receiver.extract_bug_report_from_github(event)
        if bug_report and bug_processor:
            bug_processor(bug_report)
    
    def handle_jira_issue_created(event: WebhookEvent):
        """Handle Jira issue created event."""
        bug_report = receiver.extract_bug_report_from_jira(event)
        if bug_report and bug_processor:
            bug_processor(bug_report)
    
    # Register handlers
    receiver.register_handler("github.issues.opened", handle_github_issue_opened)
    receiver.register_handler("jira.issue_created", handle_jira_issue_created)
    
    return receiver