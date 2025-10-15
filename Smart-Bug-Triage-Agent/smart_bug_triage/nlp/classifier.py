"""
Bug category classification using machine learning.
Classifies bugs into categories like Frontend, Backend, Database, etc.
"""

import pickle
import numpy as np
from typing import Dict, List, Tuple, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import logging

logger = logging.getLogger(__name__)


class BugCategoryClassifier:
    """Classifies bug reports into predefined categories."""
    
    # Predefined bug categories from design document
    CATEGORIES = [
        'Frontend/UI',
        'Backend/API', 
        'Database',
        'Mobile',
        'Security',
        'Performance'
    ]
    
    def __init__(self, model_path: str = None):
        """
        Initialize the classifier.
        
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
            max_features=5000,
            ngram_range=(1, 2),
            stop_words='english',
            lowercase=True,
            min_df=2,
            max_df=0.8
        )
        
        # Random Forest classifier
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=20,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42
        )
        
        # Create pipeline
        self.pipeline = Pipeline([
            ('tfidf', self.vectorizer),
            ('classifier', self.model)
        ])
    
    def _extract_text_features(self, preprocessed_data: Dict[str, Any]) -> str:
        """
        Extract text features for classification.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            
        Returns:
            Combined text for classification
        """
        # Combine title and description with emphasis on title
        title_weight = 2
        title_text = ' '.join([preprocessed_data['clean_title']] * title_weight)
        description_text = preprocessed_data['clean_description']
        
        # Add lemmatized tokens
        lemma_text = ' '.join(
            preprocessed_data['title_lemmas'] + 
            preprocessed_data['description_lemmas']
        )
        
        return f"{title_text} {description_text} {lemma_text}"
    
    def _get_category_keywords(self) -> Dict[str, List[str]]:
        """Get keyword patterns for each category."""
        return {
            'Frontend/UI': [
                'ui', 'frontend', 'interface', 'display', 'render', 'css', 'html',
                'react', 'vue', 'angular', 'component', 'layout', 'style', 'visual',
                'button', 'form', 'input', 'modal', 'dropdown', 'navigation', 'menu'
            ],
            'Backend/API': [
                'api', 'backend', 'server', 'endpoint', 'rest', 'graphql', 'service',
                'controller', 'route', 'middleware', 'authentication', 'authorization',
                'request', 'response', 'http', 'status', 'code', 'logic', 'business'
            ],
            'Database': [
                'database', 'db', 'sql', 'query', 'table', 'schema', 'migration',
                'mysql', 'postgresql', 'mongodb', 'redis', 'connection', 'transaction',
                'index', 'foreign', 'key', 'constraint', 'orm', 'model', 'record'
            ],
            'Mobile': [
                'mobile', 'ios', 'android', 'app', 'device', 'phone', 'tablet',
                'touch', 'gesture', 'orientation', 'responsive', 'native', 'hybrid',
                'cordova', 'react-native', 'flutter', 'xamarin', 'screen', 'resolution'
            ],
            'Security': [
                'security', 'vulnerability', 'xss', 'csrf', 'injection', 'sql injection',
                'authentication', 'authorization', 'permission', 'access', 'token',
                'encryption', 'decrypt', 'hash', 'password', 'login', 'session', 'oauth'
            ],
            'Performance': [
                'performance', 'slow', 'timeout', 'memory', 'cpu', 'load', 'speed',
                'optimization', 'cache', 'latency', 'throughput', 'bottleneck',
                'profiling', 'benchmark', 'scalability', 'resource', 'usage', 'leak'
            ]
        }
    
    def _calculate_keyword_scores(self, text: str) -> Dict[str, float]:
        """
        Calculate keyword-based scores for each category.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping categories to keyword scores
        """
        text_lower = text.lower()
        category_keywords = self._get_category_keywords()
        scores = {}
        
        for category, keywords in category_keywords.items():
            score = 0
            for keyword in keywords:
                # Count occurrences with word boundaries
                import re
                matches = len(re.findall(rf'\b{re.escape(keyword)}\b', text_lower))
                score += matches
            
            # Normalize by number of keywords
            scores[category] = score / len(keywords) if keywords else 0
        
        return scores
    
    def train(self, training_data: List[Dict[str, Any]], save_path: str = None) -> Dict[str, float]:
        """
        Train the classifier on labeled data.
        
        Args:
            training_data: List of dicts with 'preprocessed_data' and 'category'
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
            text_features = self._extract_text_features(item['preprocessed_data'])
            texts.append(text_features)
            labels.append(item['category'])
        
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
        logger.info(f"Training classifier on {len(X_train)} samples")
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
        Predict category for a bug report.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            
        Returns:
            Tuple of (predicted_category, confidence_score)
        """
        if not self.is_trained:
            # Fall back to keyword-based classification
            return self._keyword_based_prediction(preprocessed_data)
        
        # Extract text features
        text_features = self._extract_text_features(preprocessed_data)
        
        # Get prediction probabilities
        probabilities = self.pipeline.predict_proba([text_features])[0]
        predicted_idx = np.argmax(probabilities)
        confidence = probabilities[predicted_idx]
        
        predicted_category = self.pipeline.classes_[predicted_idx]
        
        return predicted_category, confidence
    
    def _keyword_based_prediction(self, preprocessed_data: Dict[str, Any]) -> Tuple[str, float]:
        """
        Fallback keyword-based prediction when no trained model is available.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            
        Returns:
            Tuple of (predicted_category, confidence_score)
        """
        text = preprocessed_data['full_text']
        keyword_scores = self._calculate_keyword_scores(text)
        
        # Find category with highest score
        best_category = max(keyword_scores.keys(), key=lambda k: keyword_scores[k])
        best_score = keyword_scores[best_category]
        
        # Convert score to confidence (normalize by max possible score)
        max_possible_score = max(len(keywords) for keywords in self._get_category_keywords().values())
        confidence = min(best_score / max_possible_score, 1.0) if max_possible_score > 0 else 0.0
        
        # If confidence is too low, default to Backend/API
        if confidence < 0.1:
            return 'Backend/API', 0.5
        
        return best_category, confidence
    
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
        
        # Get top 20 most important features
        top_indices = np.argsort(importances)[-20:]
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
            'categories': self.CATEGORIES,
            'is_trained': self.is_trained
        }
        
        with open(path, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"Model saved to {path}")
    
    def load_model(self, path: str):
        """Load a trained model from disk."""
        try:
            with open(path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.pipeline = model_data['pipeline']
            self.CATEGORIES = model_data['categories']
            self.is_trained = model_data['is_trained']
            
            logger.info(f"Model loaded from {path}")
        except Exception as e:
            logger.error(f"Failed to load model from {path}: {e}")
            self._initialize_model()