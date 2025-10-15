"""Calendar integration for developer availability detection."""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from ..models.common import AvailabilityStatus


@dataclass
class CalendarEvent:
    """Calendar event data model."""
    id: str
    title: str
    start_time: datetime
    end_time: datetime
    is_busy: bool
    is_all_day: bool
    attendees: List[str]
    location: Optional[str] = None


@dataclass
class AvailabilityWindow:
    """Availability time window."""
    start_time: datetime
    end_time: datetime
    status: AvailabilityStatus
    reason: str


class CalendarProvider(ABC):
    """Abstract base class for calendar providers."""
    
    @abstractmethod
    def get_events(
        self,
        user_email: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CalendarEvent]:
        """Get calendar events for a user in a time range."""
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """Test calendar provider connection."""
        pass


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar integration."""
    
    def __init__(self, credentials_path: str):
        """Initialize Google Calendar provider.
        
        Args:
            credentials_path: Path to Google Calendar credentials JSON
        """
        self.credentials_path = credentials_path
        self.logger = logging.getLogger(__name__)
        self._service = None
        
        try:
            self._initialize_service()
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Calendar service: {e}")
    
    def _initialize_service(self):
        """Initialize Google Calendar service."""
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            
            # Load credentials
            credentials = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=['https://www.googleapis.com/auth/calendar.readonly']
            )
            
            # Build service
            self._service = build('calendar', 'v3', credentials=credentials)
            
        except ImportError:
            self.logger.error("Google Calendar dependencies not installed. Install with: pip install google-api-python-client google-auth")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Calendar service: {e}")
            raise
    
    def get_events(
        self,
        user_email: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CalendarEvent]:
        """Get calendar events for a user."""
        if not self._service:
            return []
        
        try:
            # Format times for Google Calendar API
            time_min = start_time.isoformat() + 'Z'
            time_max = end_time.isoformat() + 'Z'
            
            # Get events
            events_result = self._service.events().list(
                calendarId=user_email,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Convert to our data model
            calendar_events = []
            for event in events:
                # Parse start and end times
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                # Handle all-day events
                is_all_day = 'date' in event['start']
                
                if is_all_day:
                    start_dt = datetime.fromisoformat(start)
                    end_dt = datetime.fromisoformat(end)
                else:
                    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                
                # Determine if event makes user busy
                is_busy = event.get('transparency', 'opaque') == 'opaque'
                
                # Get attendees
                attendees = []
                for attendee in event.get('attendees', []):
                    attendees.append(attendee.get('email', ''))
                
                calendar_event = CalendarEvent(
                    id=event['id'],
                    title=event.get('summary', 'No Title'),
                    start_time=start_dt,
                    end_time=end_dt,
                    is_busy=is_busy,
                    is_all_day=is_all_day,
                    attendees=attendees,
                    location=event.get('location')
                )
                calendar_events.append(calendar_event)
            
            self.logger.debug(f"Retrieved {len(calendar_events)} events for {user_email}")
            return calendar_events
            
        except Exception as e:
            self.logger.error(f"Failed to get calendar events for {user_email}: {e}")
            return []
    
    def test_connection(self) -> bool:
        """Test Google Calendar connection."""
        if not self._service:
            return False
        
        try:
            # Try to list calendars
            calendar_list = self._service.calendarList().list().execute()
            self.logger.info(f"Google Calendar connection successful. Found {len(calendar_list.get('items', []))} calendars")
            return True
        except Exception as e:
            self.logger.error(f"Google Calendar connection test failed: {e}")
            return False


class OutlookCalendarProvider(CalendarProvider):
    """Microsoft Outlook/Office 365 Calendar integration."""
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        """Initialize Outlook Calendar provider.
        
        Args:
            client_id: Azure AD application client ID
            client_secret: Azure AD application client secret
            tenant_id: Azure AD tenant ID
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.logger = logging.getLogger(__name__)
        self._access_token = None
    
    def _get_access_token(self) -> Optional[str]:
        """Get access token for Microsoft Graph API."""
        try:
            import requests
            
            # Token endpoint
            token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
            
            # Request data
            data = {
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            # Make request
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            self._access_token = token_data['access_token']
            return self._access_token
            
        except Exception as e:
            self.logger.error(f"Failed to get Outlook access token: {e}")
            return None
    
    def get_events(
        self,
        user_email: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CalendarEvent]:
        """Get calendar events for a user."""
        if not self._access_token:
            self._get_access_token()
        
        if not self._access_token:
            return []
        
        try:
            import requests
            
            # Microsoft Graph API endpoint
            url = f"https://graph.microsoft.com/v1.0/users/{user_email}/events"
            
            # Headers
            headers = {
                'Authorization': f'Bearer {self._access_token}',
                'Content-Type': 'application/json'
            }
            
            # Parameters
            params = {
                '$filter': f"start/dateTime ge '{start_time.isoformat()}' and end/dateTime le '{end_time.isoformat()}'",
                '$orderby': 'start/dateTime',
                '$top': 100
            }
            
            # Make request
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            events_data = response.json()
            events = events_data.get('value', [])
            
            # Convert to our data model
            calendar_events = []
            for event in events:
                # Parse times
                start_dt = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
                
                # Check if all-day event
                is_all_day = event.get('isAllDay', False)
                
                # Determine if busy
                is_busy = event.get('showAs', 'busy') in ['busy', 'tentative', 'outOfOffice']
                
                # Get attendees
                attendees = []
                for attendee in event.get('attendees', []):
                    email_address = attendee.get('emailAddress', {})
                    attendees.append(email_address.get('address', ''))
                
                calendar_event = CalendarEvent(
                    id=event['id'],
                    title=event.get('subject', 'No Title'),
                    start_time=start_dt,
                    end_time=end_dt,
                    is_busy=is_busy,
                    is_all_day=is_all_day,
                    attendees=attendees,
                    location=event.get('location', {}).get('displayName')
                )
                calendar_events.append(calendar_event)
            
            self.logger.debug(f"Retrieved {len(calendar_events)} Outlook events for {user_email}")
            return calendar_events
            
        except Exception as e:
            self.logger.error(f"Failed to get Outlook calendar events for {user_email}: {e}")
            return []
    
    def test_connection(self) -> bool:
        """Test Outlook Calendar connection."""
        try:
            token = self._get_access_token()
            if token:
                self.logger.info("Outlook Calendar connection successful")
                return True
            else:
                return False
        except Exception as e:
            self.logger.error(f"Outlook Calendar connection test failed: {e}")
            return False


class CalendarIntegration:
    """Main calendar integration class that manages multiple providers."""
    
    def __init__(self):
        """Initialize calendar integration."""
        self.providers: Dict[str, CalendarProvider] = {}
        self.logger = logging.getLogger(__name__)
    
    def add_provider(self, name: str, provider: CalendarProvider) -> bool:
        """Add a calendar provider.
        
        Args:
            name: Provider name
            provider: Calendar provider instance
            
        Returns:
            True if provider was added successfully
        """
        try:
            if provider.test_connection():
                self.providers[name] = provider
                self.logger.info(f"Added calendar provider: {name}")
                return True
            else:
                self.logger.error(f"Failed to add calendar provider {name}: connection test failed")
                return False
        except Exception as e:
            self.logger.error(f"Failed to add calendar provider {name}: {e}")
            return False
    
    def check_availability(
        self,
        user_email: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        provider_name: Optional[str] = None
    ) -> AvailabilityStatus:
        """Check user availability.
        
        Args:
            user_email: User email address
            start_time: Start time (defaults to now)
            end_time: End time (defaults to 1 hour from now)
            provider_name: Specific provider to use (uses first available if None)
            
        Returns:
            Availability status
        """
        if start_time is None:
            start_time = datetime.now()
        if end_time is None:
            end_time = start_time + timedelta(hours=1)
        
        # Select provider
        if provider_name and provider_name in self.providers:
            provider = self.providers[provider_name]
        elif self.providers:
            provider = next(iter(self.providers.values()))
        else:
            self.logger.warning("No calendar providers available")
            return AvailabilityStatus.AVAILABLE  # Default to available
        
        try:
            # Get events in the time window
            events = provider.get_events(user_email, start_time, end_time)
            
            # Check for conflicts
            for event in events:
                if event.is_busy and self._events_overlap(
                    start_time, end_time,
                    event.start_time, event.end_time
                ):
                    # Determine specific status based on event
                    if 'focus' in event.title.lower() or 'deep work' in event.title.lower():
                        return AvailabilityStatus.FOCUS_TIME
                    else:
                        return AvailabilityStatus.BUSY
            
            return AvailabilityStatus.AVAILABLE
            
        except Exception as e:
            self.logger.error(f"Failed to check availability for {user_email}: {e}")
            return AvailabilityStatus.AVAILABLE  # Default to available on error
    
    def get_availability_windows(
        self,
        user_email: str,
        start_date: datetime,
        end_date: datetime,
        provider_name: Optional[str] = None
    ) -> List[AvailabilityWindow]:
        """Get availability windows for a date range.
        
        Args:
            user_email: User email address
            start_date: Start date
            end_date: End date
            provider_name: Specific provider to use
            
        Returns:
            List of availability windows
        """
        # Select provider
        if provider_name and provider_name in self.providers:
            provider = self.providers[provider_name]
        elif self.providers:
            provider = next(iter(self.providers.values()))
        else:
            return []
        
        try:
            # Get all events in the date range
            events = provider.get_events(user_email, start_date, end_date)
            
            # Sort events by start time
            events.sort(key=lambda e: e.start_time)
            
            # Generate availability windows
            windows = []
            current_time = start_date
            
            for event in events:
                if not event.is_busy:
                    continue
                
                # Add available window before this event
                if current_time < event.start_time:
                    windows.append(AvailabilityWindow(
                        start_time=current_time,
                        end_time=event.start_time,
                        status=AvailabilityStatus.AVAILABLE,
                        reason="Free time"
                    ))
                
                # Add busy window for this event
                status = AvailabilityStatus.FOCUS_TIME if 'focus' in event.title.lower() else AvailabilityStatus.BUSY
                windows.append(AvailabilityWindow(
                    start_time=event.start_time,
                    end_time=event.end_time,
                    status=status,
                    reason=event.title
                ))
                
                current_time = max(current_time, event.end_time)
            
            # Add final available window if needed
            if current_time < end_date:
                windows.append(AvailabilityWindow(
                    start_time=current_time,
                    end_time=end_date,
                    status=AvailabilityStatus.AVAILABLE,
                    reason="Free time"
                ))
            
            return windows
            
        except Exception as e:
            self.logger.error(f"Failed to get availability windows for {user_email}: {e}")
            return []
    
    def is_in_focus_time(self, user_email: str, check_time: Optional[datetime] = None) -> bool:
        """Check if user is currently in focus time.
        
        Args:
            user_email: User email address
            check_time: Time to check (defaults to now)
            
        Returns:
            True if in focus time
        """
        if check_time is None:
            check_time = datetime.now()
        
        status = self.check_availability(
            user_email,
            check_time,
            check_time + timedelta(minutes=1)
        )
        
        return status == AvailabilityStatus.FOCUS_TIME
    
    def get_next_available_time(
        self,
        user_email: str,
        duration_minutes: int = 60,
        start_search: Optional[datetime] = None
    ) -> Optional[datetime]:
        """Find the next available time slot for a user.
        
        Args:
            user_email: User email address
            duration_minutes: Required duration in minutes
            start_search: When to start searching (defaults to now)
            
        Returns:
            Next available time or None if not found in next 7 days
        """
        if start_search is None:
            start_search = datetime.now()
        
        # Search for next 7 days
        search_end = start_search + timedelta(days=7)
        
        # Get availability windows
        windows = self.get_availability_windows(user_email, start_search, search_end)
        
        # Find first window that can accommodate the duration
        required_duration = timedelta(minutes=duration_minutes)
        
        for window in windows:
            if window.status == AvailabilityStatus.AVAILABLE:
                window_duration = window.end_time - window.start_time
                if window_duration >= required_duration:
                    return window.start_time
        
        return None
    
    def _events_overlap(
        self,
        start1: datetime,
        end1: datetime,
        start2: datetime,
        end2: datetime
    ) -> bool:
        """Check if two time periods overlap."""
        return start1 < end2 and start2 < end1