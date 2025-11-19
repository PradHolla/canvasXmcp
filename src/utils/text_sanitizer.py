"""Text sanitization utilities for handling problematic Unicode characters"""

import re
from typing import Any, Dict, List, Union


class TextSanitizer:
    """Sanitize text to prevent LLM tokenization errors and improve readability"""
    
    # Common problematic Unicode characters
    UNICODE_REPLACEMENTS = {
        '\u00a0': ' ',      # non-breaking space
        '\u202f': ' ',      # narrow no-break space (GPT-OSS issue!)
        '\u2013': '-',      # en dash
        '\u2014': '--',     # em dash
        '\u2018': "'",      # left single quote
        '\u2019': "'",      # right single quote
        '\u201c': '"',      # left double quote
        '\u201d': '"',      # right double quote
        '\u2026': '...',    # ellipsis
        '\u2022': '*',      # bullet point
        '\u2032': "'",      # prime (minute/feet)
        '\u2033': '"',      # double prime (second/inches)
    }
    
    @classmethod
    def sanitize_string(cls, text: str) -> str:
        """
        Sanitize a single string by replacing problematic Unicode characters
        
        Args:
            text: Input string
            
        Returns:
            Sanitized string
        """
        if not isinstance(text, str):
            return text
        
        # Replace known problematic characters
        for old, new in cls.UNICODE_REPLACEMENTS.items():
            text = text.replace(old, new)
        
        return text
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively sanitize all strings in a dictionary
        
        Args:
            data: Input dictionary
            
        Returns:
            Sanitized dictionary
        """
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = cls.sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = cls.sanitize_list(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    @classmethod
    def sanitize_list(cls, data: List[Any]) -> List[Any]:
        """
        Recursively sanitize all strings in a list
        
        Args:
            data: Input list
            
        Returns:
            Sanitized list
        """
        if not isinstance(data, list):
            return data
        
        sanitized = []
        for item in data:
            if isinstance(item, str):
                sanitized.append(cls.sanitize_string(item))
            elif isinstance(item, dict):
                sanitized.append(cls.sanitize_dict(item))
            elif isinstance(item, list):
                sanitized.append(cls.sanitize_list(item))
            else:
                sanitized.append(item)
        
        return sanitized
    
    @classmethod
    def sanitize(cls, data: Union[str, Dict, List]) -> Union[str, Dict, List]:
        """
        Sanitize any type of data structure
        
        Args:
            data: Input data (string, dict, or list)
            
        Returns:
            Sanitized data
        """
        if isinstance(data, str):
            return cls.sanitize_string(data)
        elif isinstance(data, dict):
            return cls.sanitize_dict(data)
        elif isinstance(data, list):
            return cls.sanitize_list(data)
        else:
            return data


def sanitize_text(text: str) -> str:
    """Convenience function for sanitizing a single string"""
    return TextSanitizer.sanitize_string(text)


def sanitize_data(data: Union[str, Dict, List]) -> Union[str, Dict, List]:
    """Convenience function for sanitizing any data structure"""
    return TextSanitizer.sanitize(data)
