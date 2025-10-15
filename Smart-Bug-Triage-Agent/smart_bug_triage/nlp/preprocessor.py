"""
Text preprocessing for bug reports.
Handles cleaning, tokenization, and normalization of bug report text.
"""

import re
import spacy
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BugTextPreprocessor:
    """Preprocesses bug report text for NLP analysis."""
    
    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Initialize the preprocessor with spaCy model.
        
        Args:
            model_name: Name of the spaCy model to use
        """
        try:
            self.nlp = spacy.load(model_name)
        except OSError:
            logger.warning(f"Model {model_name} not found, using blank model")
            self.nlp = spacy.blank("en")
        
        # Add custom patterns for technical terms
        self._setup_custom_patterns()
    
    def _setup_custom_patterns(self):
        """Set up custom patterns for technical term recognition."""
        # Add custom component for technical terms if not exists
        if "technical_terms" not in self.nlp.pipe_names:
            self.nlp.add_pipe("technical_terms", last=True)
    
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize bug report text.
        
        Args:
            text: Raw bug report text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove URLs but keep domain info
        text = re.sub(r'https?://[^\s]+', '[URL]', text)
        
        # Remove email addresses but keep domain
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
        
        # Normalize file paths
        text = re.sub(r'[A-Za-z]:\\[^\s]+', '[FILEPATH]', text)  # Windows paths
        text = re.sub(r'/[^\s]+\.[a-zA-Z0-9]+', '[FILEPATH]', text)  # Unix paths
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep technical symbols
        text = re.sub(r'[^\w\s\-\.\(\)\[\]{}:;,!?@#$%^&*+=<>/\\|`~]', '', text)
        
        return text.strip()
    
    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize text using spaCy.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of tokens
        """
        doc = self.nlp(text)
        return [token.text for token in doc if not token.is_space]
    
    def lemmatize(self, text: str) -> List[str]:
        """
        Lemmatize text and return meaningful tokens.
        
        Args:
            text: Text to lemmatize
            
        Returns:
            List of lemmatized tokens
        """
        doc = self.nlp(text)
        return [
            token.lemma_.lower() 
            for token in doc 
            if not token.is_stop 
            and not token.is_punct 
            and not token.is_space
            and len(token.text) > 2
        ]
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Extract named entities from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping entity types to lists of entities
        """
        doc = self.nlp(text)
        entities = {}
        
        for ent in doc.ents:
            if ent.label_ not in entities:
                entities[ent.label_] = []
            entities[ent.label_].append(ent.text)
        
        return entities
    
    def preprocess_for_classification(self, title: str, description: str) -> Dict[str, Any]:
        """
        Preprocess bug report for classification.
        
        Args:
            title: Bug report title
            description: Bug report description
            
        Returns:
            Dictionary with preprocessed features
        """
        # Clean both title and description
        clean_title = self.clean_text(title)
        clean_description = self.clean_text(description)
        
        # Combine for full text analysis
        full_text = f"{clean_title} {clean_description}"
        
        # Extract various features
        features = {
            'clean_title': clean_title,
            'clean_description': clean_description,
            'full_text': full_text,
            'title_tokens': self.tokenize(clean_title),
            'description_tokens': self.tokenize(clean_description),
            'title_lemmas': self.lemmatize(clean_title),
            'description_lemmas': self.lemmatize(clean_description),
            'entities': self.extract_entities(full_text),
            'text_length': len(full_text),
            'title_length': len(clean_title),
            'description_length': len(clean_description)
        }
        
        return features


@spacy.Language.component("technical_terms")
def technical_terms_component(doc):
    """Custom spaCy component for identifying technical terms."""
    # Technical patterns to identify
    technical_patterns = [
        r'\b(?:API|REST|GraphQL|JSON|XML|HTTP|HTTPS|SQL|NoSQL)\b',
        r'\b(?:React|Vue|Angular|JavaScript|TypeScript|Python|Java|C\+\+)\b',
        r'\b(?:database|DB|MySQL|PostgreSQL|MongoDB|Redis)\b',
        r'\b(?:frontend|backend|UI|UX|CSS|HTML)\b',
        r'\b(?:error|exception|bug|crash|fail|timeout)\b',
        r'\b(?:server|client|browser|mobile|desktop)\b'
    ]
    
    # Collect new entities without overlaps
    new_ents = []
    existing_spans = [(ent.start, ent.end) for ent in doc.ents]
    
    # Mark technical terms
    for pattern in technical_patterns:
        matches = re.finditer(pattern, doc.text, re.IGNORECASE)
        for match in matches:
            span = doc.char_span(match.start(), match.end(), label="TECHNICAL")
            if span:
                # Check for overlaps with existing entities
                overlaps = any(
                    span.start < end and span.end > start 
                    for start, end in existing_spans
                )
                if not overlaps:
                    new_ents.append(span)
                    existing_spans.append((span.start, span.end))
    
    # Add new entities to existing ones
    if new_ents:
        doc.ents = list(doc.ents) + new_ents
    
    return doc