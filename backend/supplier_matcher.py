"""
Supplier Name Matching Module

This module provides intelligent supplier name matching capabilities for CSV imports.
It handles fuzzy matching, name normalization, and confidence scoring to identify
existing suppliers and prevent duplicates caused by name variations.

Key Features:
- Fuzzy string matching using Levenshtein distance
- Name normalization (abbreviations, punctuation, case)
- Confidence scoring system (0-100%)
- Learning from user corrections and aliases
- Common supplier name pattern recognition

Business Logic:
- High confidence matches (>90%) can be auto-accepted
- Medium confidence matches (70-90%) require user confirmation
- Low confidence matches (<70%) require manual selection
- System learns from user mappings to improve future matches
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from difflib import SequenceMatcher
import unicodedata

try:
    from . import database
except ImportError:
    import database

logger = logging.getLogger(__name__)


class SupplierMatchError(Exception):
    """Custom exception for supplier matching operations"""
    pass


class SupplierMatcher:
    """
    Main class for intelligent supplier name matching and normalization

    This class provides comprehensive supplier name matching capabilities
    including fuzzy matching, name normalization, confidence scoring,
    and learning from user corrections.

    Attributes:
        abbreviation_map: Dictionary of common abbreviations and expansions
        stop_words: Set of words to ignore during matching
        min_confidence_threshold: Minimum confidence score for matches

    Example:
        matcher = SupplierMatcher()
        matches = matcher.find_matches("ABC Corp")
        best_match = matches[0] if matches else None
    """

    # Common supplier name abbreviations and their full forms
    ABBREVIATION_MAP = {
        'corp': 'corporation',
        'inc': 'incorporated',
        'ltd': 'limited',
        'llc': 'limited liability company',
        'co': 'company',
        'intl': 'international',
        'tech': 'technology',
        'mfg': 'manufacturing',
        'dist': 'distribution',
        'sys': 'systems',
        'sol': 'solutions',
        'grp': 'group',
        'ent': 'enterprises',
        'ind': 'industries',
        'svcs': 'services',
        'assoc': 'associates',
        'bros': 'brothers',
        'mktg': 'marketing',
        'dev': 'development',
        'res': 'research',
        'mgmt': 'management'
    }

    # Words that add little value to matching
    STOP_WORDS = {
        'the', 'and', 'or', 'of', 'in', 'at', 'to', 'for', 'with', 'by'
    }

    def __init__(self, min_confidence: float = 70.0):
        """
        Initialize the supplier matcher

        Args:
            min_confidence: Minimum confidence score for considering matches
        """
        self.min_confidence_threshold = min_confidence
        self._supplier_cache = None
        self._alias_cache = None

    def find_matches(self, supplier_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Find potential matches for a supplier name

        Searches existing suppliers and aliases for matches using fuzzy matching
        algorithms and returns scored results sorted by confidence.

        Args:
            supplier_name: The supplier name to match
            limit: Maximum number of matches to return

        Returns:
            List of match dictionaries containing:
                - supplier_id: ID of matched supplier
                - display_name: Display name of matched supplier
                - normalized_name: Normalized name that matched
                - confidence: Confidence score (0-100)
                - match_type: 'exact', 'normalized', 'fuzzy', or 'alias'
                - alias_used: If matched via alias, the alias name

        Example:
            matches = matcher.find_matches("ABC Corporation")
            if matches:
                best_match = matches[0]
                print(f"Found {best_match['display_name']} with {best_match['confidence']}% confidence")
        """
        try:
            if not supplier_name or not supplier_name.strip():
                return []

            # Normalize the input name
            normalized_input = self._normalize_name(supplier_name.strip())

            # Get all suppliers and aliases
            suppliers = self._get_suppliers()
            aliases = self._get_aliases()

            matches = []

            # Check for exact matches first
            exact_matches = self._find_exact_matches(normalized_input, suppliers, aliases)
            matches.extend(exact_matches)

            # Check for fuzzy matches
            if not exact_matches:
                fuzzy_matches = self._find_fuzzy_matches(normalized_input, suppliers, aliases)
                matches.extend(fuzzy_matches)

            # Sort by confidence score (descending) and limit results
            matches.sort(key=lambda x: x['confidence'], reverse=True)
            return matches[:limit]

        except Exception as e:
            logger.error(f"Error finding matches for supplier '{supplier_name}': {str(e)}")
            raise SupplierMatchError(f"Match search failed: {str(e)}")

    def normalize_supplier_name(self, supplier_name: str) -> str:
        """
        Normalize a supplier name for consistent storage and matching

        Applies standardization rules to create consistent normalized names
        that can be used for deduplication and matching.

        Args:
            supplier_name: Raw supplier name to normalize

        Returns:
            Normalized supplier name suitable for database storage

        Example:
            normalized = matcher.normalize_supplier_name("ABC Corp.")
            # Returns: "abc corporation"
        """
        if not supplier_name:
            return ""

        return self._normalize_name(supplier_name.strip())

    def save_mapping(self, original_name: str, supplier_id: int, confidence: float = 100.0,
                    created_by: str = 'system') -> bool:
        """
        Save a user-confirmed mapping as an alias for future reference

        When users manually map supplier names, this creates an alias record
        so the system can learn and auto-match similar names in the future.

        Args:
            original_name: The original name from import that was mapped
            supplier_id: The supplier ID it was mapped to
            confidence: Confidence score to assign to this mapping
            created_by: Username who created the mapping

        Returns:
            True if mapping was saved successfully, False otherwise

        Raises:
            SupplierMatchError: If database operation fails
        """
        try:
            connection = database.get_database_connection()
            normalized_alias = self._normalize_name(original_name)

            with connection.cursor() as cursor:
                # Check if alias already exists
                check_query = """
                    SELECT id, usage_count FROM supplier_aliases
                    WHERE normalized_alias = %s AND supplier_id = %s
                """
                cursor.execute(check_query, (normalized_alias, supplier_id))
                existing = cursor.fetchone()

                if existing:
                    # Update usage count
                    update_query = """
                        UPDATE supplier_aliases
                        SET usage_count = usage_count + 1,
                            confidence_score = GREATEST(confidence_score, %s),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """
                    cursor.execute(update_query, (confidence, existing[0]))
                else:
                    # Create new alias
                    insert_query = """
                        INSERT INTO supplier_aliases
                        (supplier_id, alias_name, normalized_alias, confidence_score, created_by)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (
                        supplier_id, original_name.strip(), normalized_alias,
                        confidence, created_by
                    ))

            connection.commit()

            # Clear cache to pick up new alias
            self._alias_cache = None

            logger.info(f"Saved supplier mapping: '{original_name}' -> supplier_id {supplier_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving supplier mapping: {str(e)}")
            raise SupplierMatchError(f"Failed to save mapping: {str(e)}")

    def create_supplier(self, display_name: str, legal_name: str = None,
                       supplier_code: str = None, created_by: str = 'system') -> int:
        """
        Create a new supplier in the master table

        Creates a new supplier record with normalized name for consistent
        matching and deduplication.

        Args:
            display_name: The display name for the supplier
            legal_name: Optional legal name (defaults to display_name)
            supplier_code: Optional supplier code
            created_by: Username who created the supplier

        Returns:
            The ID of the newly created supplier

        Raises:
            SupplierMatchError: If supplier creation fails or name already exists
        """
        try:
            if not display_name or not display_name.strip():
                raise SupplierMatchError("Display name is required")

            connection = database.get_database_connection()
            normalized_name = self._normalize_name(display_name.strip())

            # Check for existing supplier with same normalized name
            with connection.cursor() as cursor:
                check_query = "SELECT id FROM suppliers WHERE normalized_name = %s"
                cursor.execute(check_query, (normalized_name,))
                existing = cursor.fetchone()

                if existing:
                    raise SupplierMatchError(f"Supplier with similar name already exists (ID: {existing[0]})")

                # Create new supplier
                insert_query = """
                    INSERT INTO suppliers
                    (display_name, legal_name, normalized_name, supplier_code, created_by)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, (
                    display_name.strip(),
                    legal_name.strip() if legal_name else display_name.strip(),
                    normalized_name,
                    supplier_code.strip() if supplier_code else None,
                    created_by
                ))

                supplier_id = cursor.lastrowid

            connection.commit()

            # Clear cache to pick up new supplier
            self._supplier_cache = None

            logger.info(f"Created new supplier: '{display_name}' with ID {supplier_id}")
            return supplier_id

        except Exception as e:
            logger.error(f"Error creating supplier '{display_name}': {str(e)}")
            raise SupplierMatchError(f"Failed to create supplier: {str(e)}")

    def get_all_suppliers(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get all suppliers for dropdown selection

        Returns list of all suppliers suitable for display in selection dropdowns
        or mapping interfaces.

        Args:
            active_only: Whether to return only active suppliers

        Returns:
            List of supplier dictionaries with id, display_name, normalized_name
        """
        try:
            suppliers = self._get_suppliers()

            if active_only:
                suppliers = [s for s in suppliers if s.get('is_active', True)]

            return sorted(suppliers, key=lambda x: x['display_name'].lower())

        except Exception as e:
            logger.error(f"Error retrieving suppliers: {str(e)}")
            return []

    def _normalize_name(self, name: str) -> str:
        """
        Apply normalization rules to supplier name

        Args:
            name: Raw supplier name

        Returns:
            Normalized supplier name for consistent matching
        """
        if not name:
            return ""

        # Convert to lowercase
        normalized = name.lower().strip()

        # Remove accents and special characters
        normalized = unicodedata.normalize('NFKD', normalized)
        normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')

        # Remove punctuation except spaces and hyphens
        normalized = re.sub(r'[^\w\s\-]', ' ', normalized)

        # Replace multiple spaces with single space
        normalized = re.sub(r'\s+', ' ', normalized)

        # Expand common abbreviations
        words = normalized.split()
        expanded_words = []

        for word in words:
            if word in self.STOP_WORDS:
                continue  # Skip stop words
            elif word in self.ABBREVIATION_MAP:
                expanded_words.append(self.ABBREVIATION_MAP[word])
            else:
                expanded_words.append(word)

        return ' '.join(expanded_words).strip()

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity score between two strings using multiple algorithms

        Uses a combination of sequence matching and token-based comparison
        to provide robust similarity scoring.

        Args:
            str1: First string to compare
            str2: Second string to compare

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not str1 or not str2:
            return 0.0

        # Sequence matcher similarity
        seq_similarity = SequenceMatcher(None, str1, str2).ratio()

        # Token-based similarity (Jaccard similarity)
        set1 = set(str1.split())
        set2 = set(str2.split())

        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0

        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        jaccard_similarity = intersection / union if union > 0 else 0.0

        # Weighted combination (favor token-based for supplier names)
        final_score = (seq_similarity * 0.3) + (jaccard_similarity * 0.7)

        return final_score

    def _find_exact_matches(self, normalized_input: str, suppliers: List[Dict],
                           aliases: List[Dict]) -> List[Dict[str, Any]]:
        """Find exact matches in suppliers and aliases"""
        matches = []

        # Check exact match in suppliers
        for supplier in suppliers:
            if supplier['normalized_name'] == normalized_input:
                matches.append({
                    'supplier_id': supplier['id'],
                    'display_name': supplier['display_name'],
                    'normalized_name': supplier['normalized_name'],
                    'confidence': 100.0,
                    'match_type': 'exact',
                    'alias_used': None
                })

        # Check exact match in aliases
        for alias in aliases:
            if alias['normalized_alias'] == normalized_input:
                matches.append({
                    'supplier_id': alias['supplier_id'],
                    'display_name': alias['supplier_display_name'],
                    'normalized_name': alias['supplier_normalized_name'],
                    'confidence': 100.0,
                    'match_type': 'alias_exact',
                    'alias_used': alias['alias_name']
                })

        return matches

    def _find_fuzzy_matches(self, normalized_input: str, suppliers: List[Dict],
                           aliases: List[Dict]) -> List[Dict[str, Any]]:
        """Find fuzzy matches in suppliers and aliases"""
        matches = []

        # Fuzzy match against suppliers
        for supplier in suppliers:
            similarity = self._calculate_similarity(
                normalized_input,
                supplier['normalized_name']
            )
            confidence = similarity * 100

            if confidence >= self.min_confidence_threshold:
                matches.append({
                    'supplier_id': supplier['id'],
                    'display_name': supplier['display_name'],
                    'normalized_name': supplier['normalized_name'],
                    'confidence': round(confidence, 1),
                    'match_type': 'fuzzy',
                    'alias_used': None
                })

        # Fuzzy match against aliases
        for alias in aliases:
            similarity = self._calculate_similarity(
                normalized_input,
                alias['normalized_alias']
            )
            confidence = similarity * 100

            if confidence >= self.min_confidence_threshold:
                matches.append({
                    'supplier_id': alias['supplier_id'],
                    'display_name': alias['supplier_display_name'],
                    'normalized_name': alias['supplier_normalized_name'],
                    'confidence': round(confidence, 1),
                    'match_type': 'alias_fuzzy',
                    'alias_used': alias['alias_name']
                })

        return matches

    def _get_suppliers(self) -> List[Dict[str, Any]]:
        """Get all suppliers with caching"""
        if self._supplier_cache is None:
            try:
                connection = database.get_database_connection()
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, display_name, normalized_name, is_active
                        FROM suppliers
                        ORDER BY display_name
                    """)

                    self._supplier_cache = [
                        {
                            'id': row[0],
                            'display_name': row[1],
                            'normalized_name': row[2],
                            'is_active': bool(row[3])
                        }
                        for row in cursor.fetchall()
                    ]
            except Exception as e:
                logger.error(f"Error loading suppliers: {str(e)}")
                self._supplier_cache = []

        return self._supplier_cache

    def _get_aliases(self) -> List[Dict[str, Any]]:
        """Get all aliases with supplier info with caching"""
        if self._alias_cache is None:
            try:
                connection = database.get_database_connection()
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT
                            sa.supplier_id,
                            sa.alias_name,
                            sa.normalized_alias,
                            sa.confidence_score,
                            s.display_name,
                            s.normalized_name
                        FROM supplier_aliases sa
                        JOIN suppliers s ON sa.supplier_id = s.id
                        WHERE s.is_active = 1
                        ORDER BY sa.usage_count DESC, sa.confidence_score DESC
                    """)

                    self._alias_cache = [
                        {
                            'supplier_id': row[0],
                            'alias_name': row[1],
                            'normalized_alias': row[2],
                            'confidence_score': float(row[3]),
                            'supplier_display_name': row[4],
                            'supplier_normalized_name': row[5]
                        }
                        for row in cursor.fetchall()
                    ]
            except Exception as e:
                logger.error(f"Error loading aliases: {str(e)}")
                self._alias_cache = []

        return self._alias_cache

    def clear_cache(self):
        """Clear internal caches to force reload from database"""
        self._supplier_cache = None
        self._alias_cache = None


def get_supplier_matcher() -> SupplierMatcher:
    """
    Factory function to create SupplierMatcher instance

    Returns:
        Configured SupplierMatcher instance ready for use
    """
    return SupplierMatcher()