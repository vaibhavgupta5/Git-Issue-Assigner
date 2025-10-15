"""
Sample training data and utilities for training NLP models.
Provides sample bug reports for training and validation.
"""

from typing import List, Dict, Any
from .preprocessor import BugTextPreprocessor


def get_sample_classification_data() -> List[Dict[str, Any]]:
    """
    Get sample bug reports with category labels for training classification model.
    
    Returns:
        List of training samples with preprocessed_data and category
    """
    preprocessor = BugTextPreprocessor()
    
    # Sample bug reports with categories
    sample_bugs = [
        # Frontend/UI bugs
        {
            'title': 'Button not displaying correctly on mobile devices',
            'description': 'The submit button appears cut off on iPhone and Android devices. CSS styling seems broken for small screens. Users cannot complete form submission.',
            'category': 'Frontend/UI'
        },
        {
            'title': 'React component rendering blank page',
            'description': 'After updating to React 18, the UserProfile component shows a blank page. Console shows no errors. Component worked fine in React 17.',
            'category': 'Frontend/UI'
        },
        {
            'title': 'CSS layout broken in Safari browser',
            'description': 'The navigation menu overlaps with content in Safari. Works fine in Chrome and Firefox. Using flexbox layout.',
            'category': 'Frontend/UI'
        },
        
        # Backend/API bugs
        {
            'title': 'API endpoint returning 500 internal server error',
            'description': 'The /api/users endpoint is throwing 500 errors intermittently. Server logs show database connection timeout. Affects user authentication flow.',
            'category': 'Backend/API'
        },
        {
            'title': 'REST API response missing required fields',
            'description': 'The user profile API is not returning the email field in the JSON response. Frontend expects this field for display.',
            'category': 'Backend/API'
        },
        {
            'title': 'Authentication middleware failing',
            'description': 'JWT token validation is failing for valid tokens. Users getting 401 unauthorized errors. Token expiry logic seems incorrect.',
            'category': 'Backend/API'
        },
        
        # Database bugs
        {
            'title': 'Database migration failing on production',
            'description': 'Migration script 20231201_add_user_preferences.sql is failing with foreign key constraint error. Works fine on development database.',
            'category': 'Database'
        },
        {
            'title': 'SQL query performance degradation',
            'description': 'The user search query is taking 30+ seconds to execute. Database has grown to 1M+ records. Need query optimization or indexing.',
            'category': 'Database'
        },
        {
            'title': 'PostgreSQL connection pool exhausted',
            'description': 'Application running out of database connections during peak hours. Connection pool size is 20. Getting connection timeout errors.',
            'category': 'Database'
        },
        
        # Mobile bugs
        {
            'title': 'iOS app crashing on device rotation',
            'description': 'React Native app crashes when user rotates device from portrait to landscape. Only happens on iOS 16+. Android works fine.',
            'category': 'Mobile'
        },
        {
            'title': 'Android push notifications not working',
            'description': 'Firebase push notifications are not being received on Android devices. iOS notifications work correctly. FCM token generation seems fine.',
            'category': 'Mobile'
        },
        {
            'title': 'Touch gestures not responsive on tablet',
            'description': 'Swipe gestures for navigation are not working properly on iPad. Requires multiple attempts to register touch events.',
            'category': 'Mobile'
        },
        
        # Security bugs
        {
            'title': 'XSS vulnerability in comment section',
            'description': 'User comments are not being sanitized properly. Script tags are being executed when comments are displayed. Potential security risk.',
            'category': 'Security'
        },
        {
            'title': 'SQL injection possible in search endpoint',
            'description': 'The search API is vulnerable to SQL injection attacks. User input is not being parameterized in the database query.',
            'category': 'Security'
        },
        {
            'title': 'Session tokens not expiring properly',
            'description': 'User session tokens remain valid even after logout. Security concern as tokens could be reused if intercepted.',
            'category': 'Security'
        },
        
        # Performance bugs
        {
            'title': 'Page load time extremely slow',
            'description': 'Homepage is taking 15+ seconds to load. Large JavaScript bundles and unoptimized images causing performance issues.',
            'category': 'Performance'
        },
        {
            'title': 'Memory leak in background process',
            'description': 'Server memory usage keeps increasing over time. Background job processor not releasing memory after task completion.',
            'category': 'Performance'
        },
        {
            'title': 'API response time degrading',
            'description': 'API endpoints are responding slower than usual. Average response time increased from 200ms to 2000ms over past week.',
            'category': 'Performance'
        }
    ]
    
    # Preprocess all samples
    training_data = []
    for bug in sample_bugs:
        preprocessed_data = preprocessor.preprocess_for_classification(
            bug['title'], 
            bug['description']
        )
        training_data.append({
            'preprocessed_data': preprocessed_data,
            'category': bug['category']
        })
    
    return training_data


def get_sample_severity_data() -> List[Dict[str, Any]]:
    """
    Get sample bug reports with severity labels for training severity prediction model.
    
    Returns:
        List of training samples with preprocessed_data and severity
    """
    preprocessor = BugTextPreprocessor()
    
    # Sample bug reports with severity levels
    sample_bugs = [
        # Critical severity
        {
            'title': 'Production server completely down',
            'description': 'All production servers are offline. Users cannot access the application. Database connection failed. Urgent fix needed immediately!',
            'severity': 'Critical'
        },
        {
            'title': 'Security breach - user data exposed',
            'description': 'Critical security vulnerability exploited. User personal data including passwords may be compromised. Immediate action required.',
            'severity': 'Critical'
        },
        {
            'title': 'Payment system not processing transactions',
            'description': 'Payment gateway is down. No transactions are being processed. Revenue impact is significant. All customers affected.',
            'severity': 'Critical'
        },
        
        # High severity
        {
            'title': 'Login system failing for 50% of users',
            'description': 'Authentication service is intermittently failing. About half of login attempts result in errors. Significant user impact.',
            'severity': 'High'
        },
        {
            'title': 'Data corruption in user profiles',
            'description': 'User profile data is being corrupted during updates. Several users have reported missing information. Data integrity issue.',
            'severity': 'High'
        },
        {
            'title': 'API returning incorrect data',
            'description': 'The user API is returning wrong user information. Users seeing other people\'s data. Privacy and functionality issue.',
            'severity': 'High'
        },
        
        # Medium severity
        {
            'title': 'Search functionality not working properly',
            'description': 'Search results are incomplete or irrelevant. Users can still navigate manually but search experience is poor.',
            'severity': 'Medium'
        },
        {
            'title': 'Email notifications delayed',
            'description': 'Email notifications are being sent with 2-3 hour delay. Not critical but affects user experience.',
            'severity': 'Medium'
        },
        {
            'title': 'Mobile app UI elements misaligned',
            'description': 'Some buttons and text are not properly aligned on mobile devices. Functional but looks unprofessional.',
            'severity': 'Medium'
        },
        
        # Low severity
        {
            'title': 'Typo in footer text',
            'description': 'There is a spelling mistake in the footer copyright text. Minor cosmetic issue that should be fixed when convenient.',
            'severity': 'Low'
        },
        {
            'title': 'Tooltip text could be more descriptive',
            'description': 'The help tooltip for the save button could provide more detailed information. Enhancement suggestion.',
            'severity': 'Low'
        },
        {
            'title': 'Console warning messages',
            'description': 'Browser console shows some deprecation warnings. No functional impact but should be addressed eventually.',
            'severity': 'Low'
        }
    ]
    
    # Preprocess all samples
    training_data = []
    for bug in sample_bugs:
        preprocessed_data = preprocessor.preprocess_for_classification(
            bug['title'], 
            bug['description']
        )
        training_data.append({
            'preprocessed_data': preprocessed_data,
            'severity': bug['severity']
        })
    
    return training_data


def create_training_dataset() -> Dict[str, List[Dict[str, Any]]]:
    """
    Create a complete training dataset for both classification and severity prediction.
    
    Returns:
        Dictionary with 'classification' and 'severity' training data
    """
    return {
        'classification': get_sample_classification_data(),
        'severity': get_sample_severity_data()
    }


def validate_training_data(training_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Validate the training data for completeness and quality.
    
    Args:
        training_data: Training dataset
        
    Returns:
        Validation results
    """
    results = {
        'classification': {
            'sample_count': 0,
            'categories': set(),
            'valid_samples': 0
        },
        'severity': {
            'sample_count': 0,
            'severity_levels': set(),
            'valid_samples': 0
        }
    }
    
    # Validate classification data
    if 'classification' in training_data:
        class_data = training_data['classification']
        results['classification']['sample_count'] = len(class_data)
        
        for sample in class_data:
            if 'preprocessed_data' in sample and 'category' in sample:
                results['classification']['valid_samples'] += 1
                results['classification']['categories'].add(sample['category'])
    
    # Validate severity data
    if 'severity' in training_data:
        sev_data = training_data['severity']
        results['severity']['sample_count'] = len(sev_data)
        
        for sample in sev_data:
            if 'preprocessed_data' in sample and 'severity' in sample:
                results['severity']['valid_samples'] += 1
                results['severity']['severity_levels'].add(sample['severity'])
    
    # Convert sets to lists for JSON serialization
    results['classification']['categories'] = list(results['classification']['categories'])
    results['severity']['severity_levels'] = list(results['severity']['severity_levels'])
    
    return results