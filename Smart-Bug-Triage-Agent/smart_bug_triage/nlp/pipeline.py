"""
Main NLP pipeline that integrates all NLP components.
Provides a unified interface for bug report analysis.
"""

from typing import Dict, Any, Optional, Tuple, List
import logging
from .preprocessor import BugTextPreprocessor
from .classifier import BugCategoryClassifier
from .severity_predictor import SeverityPredictor
from .keyword_extractor import KeywordExtractor

logger = logging.getLogger(__name__)


class NLPPipeline:
    """
    Main NLP pipeline for bug triage analysis.
    Integrates preprocessing, classification, severity prediction, and keyword extraction.
    """
    
    def __init__(self, 
                 spacy_model: str = "en_core_web_sm",
                 classifier_model_path: Optional[str] = None,
                 severity_model_path: Optional[str] = None):
        """
        Initialize the NLP pipeline.
        
        Args:
            spacy_model: Name of the spaCy model to use
            classifier_model_path: Path to trained classifier model
            severity_model_path: Path to trained severity model
        """
        self.preprocessor = BugTextPreprocessor(spacy_model)
        self.classifier = BugCategoryClassifier(classifier_model_path)
        self.severity_predictor = SeverityPredictor(severity_model_path)
        self.keyword_extractor = KeywordExtractor(spacy_model)
        
        logger.info("NLP Pipeline initialized")
    
    def analyze_bug_report(self, title: str, description: str) -> Dict[str, Any]:
        """
        Perform complete analysis of a bug report.
        
        Args:
            title: Bug report title
            description: Bug report description
            
        Returns:
            Dictionary containing all analysis results
        """
        try:
            # Step 1: Preprocess the text
            logger.debug("Preprocessing bug report text")
            preprocessed_data = self.preprocessor.preprocess_for_classification(title, description)
            
            # Step 2: Extract keywords and technical terms
            logger.debug("Extracting keywords and technical terms")
            keywords = self.keyword_extractor.extract_all_keywords(preprocessed_data)
            
            # Step 3: Classify bug category
            logger.debug("Classifying bug category")
            category, category_confidence = self.classifier.predict(preprocessed_data)
            
            # Step 4: Predict severity
            logger.debug("Predicting bug severity")
            severity, severity_confidence = self.severity_predictor.predict(preprocessed_data)
            
            # Step 5: Compile results
            analysis_result = {
                'preprocessing': {
                    'clean_title': preprocessed_data['clean_title'],
                    'clean_description': preprocessed_data['clean_description'],
                    'text_length': preprocessed_data['text_length'],
                    'entities': preprocessed_data['entities']
                },
                'classification': {
                    'category': category,
                    'confidence': category_confidence,
                    'available_categories': self.classifier.CATEGORIES
                },
                'severity': {
                    'level': severity,
                    'confidence': severity_confidence,
                    'available_levels': self.severity_predictor.SEVERITY_LEVELS
                },
                'keywords': keywords,
                'analysis_metadata': {
                    'classifier_trained': self.classifier.is_trained,
                    'severity_predictor_trained': self.severity_predictor.is_trained,
                    'processing_successful': True
                }
            }
            
            logger.info(f"Bug analysis completed: Category={category} ({category_confidence:.2f}), "
                       f"Severity={severity} ({severity_confidence:.2f})")
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing bug report: {e}")
            return self._create_error_result(title, description, str(e))
    
    def _create_error_result(self, title: str, description: str, error_message: str) -> Dict[str, Any]:
        """
        Create a fallback result when analysis fails.
        
        Args:
            title: Original bug title
            description: Original bug description
            error_message: Error that occurred
            
        Returns:
            Fallback analysis result
        """
        return {
            'preprocessing': {
                'clean_title': title,
                'clean_description': description,
                'text_length': len(title) + len(description),
                'entities': {}
            },
            'classification': {
                'category': 'Backend/API',  # Default fallback
                'confidence': 0.3,
                'available_categories': self.classifier.CATEGORIES
            },
            'severity': {
                'level': 'Medium',  # Default fallback
                'confidence': 0.3,
                'available_levels': self.severity_predictor.SEVERITY_LEVELS
            },
            'keywords': {
                'technical_terms': {},
                'error_patterns': [],
                'file_references': [],
                'version_numbers': [],
                'important_keywords': [],
                'entities': {},
                'summary': {
                    'top_keywords': [],
                    'technical_categories': [],
                    'primary_language': None,
                    'has_errors': False,
                    'has_stack_trace': False,
                    'complexity_indicators': {
                        'technical_term_count': 0,
                        'error_count': 0,
                        'keyword_diversity': 0
                    }
                }
            },
            'analysis_metadata': {
                'classifier_trained': self.classifier.is_trained,
                'severity_predictor_trained': self.severity_predictor.is_trained,
                'processing_successful': False,
                'error_message': error_message
            }
        }
    
    def get_confidence_threshold_recommendation(self, analysis_result: Dict[str, Any]) -> Dict[str, bool]:
        """
        Recommend whether the analysis results meet confidence thresholds.
        
        Args:
            analysis_result: Result from analyze_bug_report
            
        Returns:
            Dictionary with threshold recommendations
        """
        category_confidence = analysis_result['classification']['confidence']
        severity_confidence = analysis_result['severity']['confidence']
        
        # Thresholds from requirements (70% for category, similar for severity)
        category_threshold = 0.7
        severity_threshold = 0.6
        
        return {
            'category_meets_threshold': category_confidence >= category_threshold,
            'severity_meets_threshold': severity_confidence >= severity_threshold,
            'overall_confidence_acceptable': (
                category_confidence >= category_threshold and 
                severity_confidence >= severity_threshold
            ),
            'requires_manual_review': (
                category_confidence < category_threshold or 
                severity_confidence < severity_threshold
            ),
            'thresholds': {
                'category_threshold': category_threshold,
                'severity_threshold': severity_threshold
            }
        }
    
    def train_models(self, training_data: Dict[str, Any], model_save_dir: str = "models/") -> Dict[str, Any]:
        """
        Train both classification and severity prediction models.
        
        Args:
            training_data: Dictionary with 'classification' and 'severity' training data
            model_save_dir: Directory to save trained models
            
        Returns:
            Training results for both models
        """
        results = {}
        
        # Train classifier if data provided
        if 'classification' in training_data and training_data['classification']:
            logger.info("Training bug category classifier")
            classifier_path = f"{model_save_dir}/bug_classifier.pkl"
            classifier_results = self.classifier.train(
                training_data['classification'], 
                classifier_path
            )
            results['classifier'] = classifier_results
        
        # Train severity predictor if data provided
        if 'severity' in training_data and training_data['severity']:
            logger.info("Training severity predictor")
            severity_path = f"{model_save_dir}/severity_predictor.pkl"
            severity_results = self.severity_predictor.train(
                training_data['severity'],
                severity_path
            )
            results['severity_predictor'] = severity_results
        
        return results
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current models.
        
        Returns:
            Dictionary with model information
        """
        return {
            'classifier': {
                'is_trained': self.classifier.is_trained,
                'categories': self.classifier.CATEGORIES,
                'feature_importance': self.classifier.get_feature_importance() if self.classifier.is_trained else {}
            },
            'severity_predictor': {
                'is_trained': self.severity_predictor.is_trained,
                'severity_levels': self.severity_predictor.SEVERITY_LEVELS,
                'feature_importance': self.severity_predictor.get_feature_importance() if self.severity_predictor.is_trained else {}
            },
            'preprocessor': {
                'spacy_model': self.preprocessor.nlp.meta.get('name', 'unknown') if hasattr(self.preprocessor.nlp, 'meta') else 'blank'
            }
        }
    
    def validate_analysis_quality(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate the quality of analysis results.
        
        Args:
            analysis_result: Result from analyze_bug_report
            
        Returns:
            Quality validation results
        """
        quality_checks = {
            'has_meaningful_keywords': len(analysis_result['keywords']['summary']['top_keywords']) > 0,
            'has_technical_terms': analysis_result['keywords']['summary']['complexity_indicators']['technical_term_count'] > 0,
            'text_length_adequate': analysis_result['preprocessing']['text_length'] > 20,
            'category_confidence_acceptable': analysis_result['classification']['confidence'] > 0.5,
            'severity_confidence_acceptable': analysis_result['severity']['confidence'] > 0.5,
            'processing_successful': analysis_result['analysis_metadata']['processing_successful']
        }
        
        # Calculate overall quality score
        passed_checks = sum(1 for check in quality_checks.values() if check)
        total_checks = len(quality_checks)
        quality_score = passed_checks / total_checks
        
        return {
            'quality_checks': quality_checks,
            'quality_score': quality_score,
            'quality_level': (
                'High' if quality_score >= 0.8 else
                'Medium' if quality_score >= 0.6 else
                'Low'
            ),
            'recommendations': self._get_quality_recommendations(quality_checks)
        }
    
    def _get_quality_recommendations(self, quality_checks: Dict[str, bool]) -> List[str]:
        """
        Get recommendations based on quality check results.
        
        Args:
            quality_checks: Results from quality validation
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        if not quality_checks['has_meaningful_keywords']:
            recommendations.append("Consider adding more descriptive keywords to the bug report")
        
        if not quality_checks['has_technical_terms']:
            recommendations.append("Include technical details and specific technologies involved")
        
        if not quality_checks['text_length_adequate']:
            recommendations.append("Provide more detailed description of the issue")
        
        if not quality_checks['category_confidence_acceptable']:
            recommendations.append("Classification confidence is low - consider manual review")
        
        if not quality_checks['severity_confidence_acceptable']:
            recommendations.append("Severity prediction confidence is low - consider manual review")
        
        if not quality_checks['processing_successful']:
            recommendations.append("Analysis failed - check input format and try again")
        
        return recommendations