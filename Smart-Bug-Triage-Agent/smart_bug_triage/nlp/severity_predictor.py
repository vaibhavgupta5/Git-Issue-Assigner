"""
Severity prediction for bug reports.
Predicts severity levels (Critical, High, Medium, Low) based on keywords and patterns.
"""

import re
import pickle
import numpy as np
from typing import Dict, List, Tuple, Any
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import logging

logger = logging.getLogger(__name__)


class SeverityPredictor:
    """Predicts bug severity based on text analysis and patterns."""
    
    # Severity levels from design document
    SEVERITY_LEVELS = ['Critical', 'High', 'Medium', 'Low']
    
    def __init__(self, model_path: str = None):
        """
        Initialize the severity predictor.
        
        Args:
            model_path: Path to saved model file
        """
        self.model = None
        self.vectorizer = None
        self.pipeline = None
        self.is_trained = False
        
        if model_path:
            self.load_model(model_path)
        else:
            self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the ML pipeline."""
        # TF-IDF vectorizer for text features
        self.vectorizer = TfidfVectorizer(
            max_features=3000,
            ngram_range=(1, 3),
            stop_words='english',
            lowercase=True,
            min_df=1,
            max_df=0.9
        )
        
        # Gradient Boosting classifier
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=6,
            random_state=42
        )
        
        # Create pipeline
        self.pipeline = Pipeline([
            ('tfidf', self.vectorizer),
            ('classifier', self.model)
        ])
    
    def _get_severity_keywords(self) -> Dict[str, Dict[str, List[str]]]:
        """Get keyword patterns for each severity level."""
        return {
            'Critical': {
                'impact': [
                    'crash', 'crashes', 'crashing', 'down', 'outage', 'offline',
                    'broken', 'fails', 'failure', 'dead', 'corrupt', 'corrupted',
                    'data loss', 'security breach', 'vulnerability', 'exploit'
                ],
                'urgency': [
                    'urgent', 'critical', 'emergency', 'immediately', 'asap',
                    'production', 'live', 'customer', 'users affected', 'blocking'
                ],
                'scope': [
                    'all users', 'entire system', 'complete', 'total', 'whole',
                    'everyone', 'site wide', 'global', 'major'
                ]
            },
            'High': {
                'impact': [
                    'error', 'exception', 'bug', 'issue', 'problem', 'wrong',
                    'incorrect', 'missing', 'not working', 'broken feature'
                ],
                'urgency': [
                    'important', 'priority', 'soon', 'needed', 'required',
                    'affecting', 'impacting', 'significant'
                ],
                'scope': [
                    'many users', 'multiple', 'several', 'some users',
                    'feature', 'functionality', 'workflow'
                ]
            },
            'Medium': {
                'impact': [
                    'minor', 'small', 'cosmetic', 'ui', 'display', 'formatting',
                    'layout', 'style', 'appearance', 'visual'
                ],
                'urgency': [
                    'when possible', 'eventually', 'nice to have',
                    'improvement', 'enhancement', 'optimize'
                ],
                'scope': [
                    'few users', 'specific', 'particular', 'edge case',
                    'certain conditions', 'sometimes'
                ]
            },
            'Low': {
                'impact': [
                    'typo', 'spelling', 'grammar', 'text', 'wording',
                    'suggestion', 'idea', 'feature request', 'enhancement'
                ],
                'urgency': [
                    'low priority', 'future', 'someday', 'maybe',
                    'consider', 'could', 'might', 'optional'
                ],
                'scope': [
                    'single user', 'rare', 'uncommon', 'unlikely',
                    'documentation', 'comment', 'log'
                ]
            }
        }
    
    def _extract_severity_features(self, preprocessed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract features relevant to severity prediction.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            
        Returns:
            Dictionary of severity-related features
        """
        title = preprocessed_data['clean_title'].lower()
        description = preprocessed_data['clean_description'].lower()
        full_text = preprocessed_data['full_text'].lower()
        
        features = {
            'text': full_text,
            'title_length': len(title),
            'description_length': len(description),
            'has_stack_trace': bool(re.search(r'traceback|stack trace|at line|error:|exception:', full_text)),
            'has_error_codes': bool(re.search(r'\b\d{3,4}\b|error \d+|code \d+', full_text)),
            'has_urls': '[URL]' in full_text,
            'has_file_paths': '[FILEPATH]' in full_text,
            'exclamation_count': full_text.count('!'),
            'question_count': full_text.count('?'),
            'caps_ratio': sum(1 for c in preprocessed_data['full_text'] if c.isupper()) / max(len(preprocessed_data['full_text']), 1)
        }
        
        # Add keyword-based features
        severity_keywords = self._get_severity_keywords()
        for severity, categories in severity_keywords.items():
            for category, keywords in categories.items():
                feature_name = f'{severity.lower()}_{category}_score'
                score = sum(1 for keyword in keywords if keyword in full_text)
                features[feature_name] = score / len(keywords) if keywords else 0
        
        return features
    
    def _calculate_keyword_scores(self, preprocessed_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate keyword-based severity scores.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            
        Returns:
            Dictionary mapping severity levels to scores
        """
        full_text = preprocessed_data['full_text'].lower()
        severity_keywords = self._get_severity_keywords()
        scores = {}
        
        for severity, categories in severity_keywords.items():
            total_score = 0
            total_keywords = 0
            
            for category, keywords in categories.items():
                category_score = 0
                for keyword in keywords:
                    # Count occurrences with word boundaries
                    matches = len(re.findall(rf'\b{re.escape(keyword)}\b', full_text))
                    category_score += matches
                
                # Weight different categories
                weights = {'impact': 3, 'urgency': 2, 'scope': 1}
                weight = weights.get(category, 1)
                total_score += category_score * weight
                total_keywords += len(keywords) * weight
            
            # Normalize score
            scores[severity] = total_score / total_keywords if total_keywords > 0 else 0
        
        return scores
    
    def _rule_based_prediction(self, preprocessed_data: Dict[str, Any]) -> Tuple[str, float]:
        """
        Rule-based severity prediction using patterns and keywords.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            
        Returns:
            Tuple of (predicted_severity, confidence_score)
        """
        features = self._extract_severity_features(preprocessed_data)
        keyword_scores = self._calculate_keyword_scores(preprocessed_data)
        
        # Apply rules based on features
        confidence = 0.5  # Base confidence
        
        # Critical indicators
        if (features['has_stack_trace'] and 
            any(word in features['text'] for word in ['crash', 'down', 'outage', 'security'])):
            return 'Critical', 0.8
        
        # High severity indicators
        if (features['has_error_codes'] or 
            features['exclamation_count'] > 2 or
            features['caps_ratio'] > 0.3):
            if keyword_scores.get('Critical', 0) > keyword_scores.get('High', 0):
                return 'Critical', 0.7
            return 'High', 0.7
        
        # Use keyword scores
        best_severity = max(keyword_scores.keys(), key=lambda k: keyword_scores[k])
        best_score = keyword_scores[best_severity]
        
        # Adjust confidence based on score strength
        if best_score > 0.3:
            confidence = 0.8
        elif best_score > 0.1:
            confidence = 0.6
        else:
            confidence = 0.4
            # Default to Medium if no strong indicators
            best_severity = 'Medium'
        
        return best_severity, confidence
    
    def train(self, training_data: List[Dict[str, Any]], save_path: str = None) -> Dict[str, float]:
        """
        Train the severity predictor on labeled data.
        
        Args:
            training_data: List of dicts with 'preprocessed_data' and 'severity'
            save_path: Path to save the trained model
            
        Returns:
            Training metrics
        """
        if not training_data:
            raise ValueError("Training data cannot be empty")
        
        # Extract features and labels
        texts = []
        labels = []
        
        for item in training_data:
            features = self._extract_severity_features(item['preprocessed_data'])
            texts.append(features['text'])
            labels.append(item['severity'])
        
        # Split data - adjust test size for small datasets
        test_size = min(0.2, max(0.1, len(texts) // 10))
        if len(texts) < 10:
            # For very small datasets, don't use stratification
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=test_size, random_state=42
            )
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=test_size, random_state=42, stratify=labels
            )
        
        # Train the model
        logger.info(f"Training severity predictor on {len(X_train)} samples")
        self.pipeline.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.pipeline.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        
        logger.info(f"Training completed. Accuracy: {accuracy:.3f}")
        logger.info(f"Classification report:\n{classification_report(y_test, y_pred)}")
        
        self.is_trained = True
        
        # Save model if path provided
        if save_path:
            self.save_model(save_path)
        
        return {
            'accuracy': accuracy,
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }
    
    def predict(self, preprocessed_data: Dict[str, Any]) -> Tuple[str, float]:
        """
        Predict severity for a bug report.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            
        Returns:
            Tuple of (predicted_severity, confidence_score)
        """
        if not self.is_trained:
            # Fall back to rule-based prediction
            return self._rule_based_prediction(preprocessed_data)
        
        # Extract features
        features = self._extract_severity_features(preprocessed_data)
        
        # Get prediction probabilities
        probabilities = self.pipeline.predict_proba([features['text']])[0]
        predicted_idx = np.argmax(probabilities)
        confidence = probabilities[predicted_idx]
        
        predicted_severity = self.pipeline.classes_[predicted_idx]
        
        return predicted_severity, confidence
    
    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get feature importance from the trained model.
        
        Returns:
            Dictionary mapping features to importance scores
        """
        if not self.is_trained or not hasattr(self.pipeline.named_steps['classifier'], 'feature_importances_'):
            return {}
        
        feature_names = self.pipeline.named_steps['tfidf'].get_feature_names_out()
        importances = self.pipeline.named_steps['classifier'].feature_importances_
        
        # Get top 15 most important features
        top_indices = np.argsort(importances)[-15:]
        return {
            feature_names[i]: importances[i] 
            for i in top_indices
        }
    
    def save_model(self, path: str):
        """Save the trained model to disk."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        model_data = {
            'pipeline': self.pipeline,
            'severity_levels': self.SEVERITY_LEVELS,
            'is_trained': self.is_trained
        }
        
        with open(path, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"Severity model saved to {path}")
    
    def load_model(self, path: str):
        """Load a trained model from disk."""
        try:
            with open(path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.pipeline = model_data['pipeline']
            self.SEVERITY_LEVELS = model_data['severity_levels']
            self.is_trained = model_data['is_trained']
            
            logger.info(f"Severity model loaded from {path}")
        except Exception as e:
            logger.error(f"Failed to load severity model from {path}: {e}")
            self._initialize_model()