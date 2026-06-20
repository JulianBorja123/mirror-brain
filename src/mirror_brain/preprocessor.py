"""
TextPreprocessor: normalizes, splits, and estimates complexity of text.

No external dependencies. The optional `llm_call` parameter allows LLM-enhanced
processing, but every method degrades gracefully to pure-heuristic mode when
`llm_call` is None (the default).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Topic-transition markers (Spanish + English).  Each tuple is (regex pattern, theme label).
_TOPIC_MARKERS: list[tuple[str, str]] = [
    # Spanish
    (r"\bAhora bien\b", "transition"),
    (r"\bPor otro lado\b", "contrast"),
    (r"\bEn cuanto a\b", "topic_shift"),
    (r"\bRespecto a\b", "topic_shift"),
    (r"\bCon respecto a\b", "topic_shift"),
    (r"\bEn relación con\b", "topic_shift"),
    (r"\bFinalmente\b", "conclusion"),
    (r"\bPor último\b", "conclusion"),
    (r"\bEn conclusión\b", "conclusion"),
    (r"\bEn resumen\b", "summary"),
    (r"\bPara empezar\b", "introduction"),
    (r"\bEn primer lugar\b", "introduction"),
    (r"\bA continuación\b", "continuation"),
    (r"\bAdemás\b", "addition"),
    (r"\bSin embargo\b", "contrast"),
    (r"\bNo obstante\b", "contrast"),
    (r"\bPor lo tanto\b", "consequence"),
    (r"\bPor consiguiente\b", "consequence"),
    (r"\bAsimismo\b", "addition"),
    (r"\bPor ejemplo\b", "example"),
    (r"\bEs decir\b", "clarification"),
    (r"\bO sea\b", "clarification"),
    (r"\bCabe destacar\b", "emphasis"),
    (r"\bCabe mencionar\b", "emphasis"),
    (r"\bPor su parte\b", "topic_shift"),
    (r"\bEn cambio\b", "contrast"),
    (r"\bMientras tanto\b", "temporal"),
    (r"\bMientras que\b", "contrast"),
    (r"\bPor el contrario\b", "contrast"),
    (r"\bA pesar de\b", "contrast"),
    (r"\bAunque\b", "contrast"),
    (r"\bPor supuesto\b", "emphasis"),
    (r"\bDesde luego\b", "emphasis"),
    (r"\bEn definitiva\b", "conclusion"),
    (r"\bEn todo caso\b", "clarification"),
    (r"\bSea como sea\b", "clarification"),
    # English
    (r"\bHowever\b", "contrast"),
    (r"\bMoreover\b", "addition"),
    (r"\bFurthermore\b", "addition"),
    (r"\bOn the other hand\b", "contrast"),
    (r"\bIn conclusion\b", "conclusion"),
    (r"\bFinally\b", "conclusion"),
    (r"\bAdditionally\b", "addition"),
    (r"\bNevertheless\b", "contrast"),
    (r"\bRegarding\b", "topic_shift"),
    (r"\bConcerning\b", "topic_shift"),
    (r"\bTo begin with\b", "introduction"),
    (r"\bIn summary\b", "summary"),
    (r"\bFor example\b", "example"),
    (r"\bFor instance\b", "example"),
    (r"\bIn other words\b", "clarification"),
    (r"\bThat is to say\b", "clarification"),
    (r"\bAs a result\b", "consequence"),
    (r"\bTherefore\b", "consequence"),
    (r"\bIn contrast\b", "contrast"),
    (r"\bBy contrast\b", "contrast"),
    (r"\bMeanwhile\b", "temporal"),
    (r"\bSubsequently\b", "temporal"),
    (r"\bAs well as\b", "addition"),
    (r"\bIn addition\b", "addition"),
    (r"\bFirst\b", "introduction"),
    (r"\bSecondly\b", "continuation"),
    (r"\bThirdly\b", "continuation"),
    (r"\bLastly\b", "conclusion"),
    (r"\bFirst of all\b", "introduction"),
]

# Connector words used as sentence boundaries in all-lowercase transcription text
_TRANSCRIPTION_CONNECTORS: list[str] = [
    "entonces",
    "bueno",
    " y ",
    " pero ",
    " porque ",
    "además",
    "también",
    "ahora",
    "después",
    "así que",
    "o sea",
    "sin embargo",
    "entonces a",
    "y si",
    "pero la",
    "bueno ahora",
]

# Spanish filler words / muletillas
_SPANISH_FILLERS: set[str] = {
    "bueno", "pues", "entonces", "digamos", "eh", "este", "esto",
    "a ver", "vale", "vamos", "mira", "claro", "hombre",
    "pues nada", "en plan", "tipo", "como que", "o sea",
    "la verdad", "yo creo", "yo pienso", "sabes", "entiendes",
    "no sé", "es que", "bueno pues", "pues eso", "y tal",
    "y eso", "y nada", "pues bien", "así que", "total que",
}

# English filler words
_ENGLISH_FILLERS: set[str] = {
    "um", "uh", "like", "you know", "i mean", "well", "so",
    "actually", "basically", "literally", "right", "okay",
    "anyway", "stuff", "things", "kind of", "sort of",
    "you see", "i guess", "i think", "you know what i mean",
    "honestly", "frankly", "apparently", "supposedly",
}

# Spanish emotional / affective keywords (lowercase)
_SPANISH_EMOTIONAL: set[str] = {
    "feliz", "felicidad", "alegría", "alegre", "contento", "contenta",
    "triste", "tristeza", "deprimido", "depresión", "melancolía",
    "enojado", "enojada", "enojo", "ira", "furioso", "rabia",
    "asustado", "asustada", "miedo", "aterrorizado", "terror", "pánico",
    "sorprendido", "sorpresa", "asombro", "asombrado",
    "amor", "amar", "cariño", "afecto", "querer", "adorar",
    "odio", "odiar", "desprecio", "repulsión", "asco",
    "ansiedad", "ansioso", "nervioso", "nervios", "preocupado",
    "calma", "tranquilo", "sereno", "paz", "serenidad",
    "esperanza", "esperanzado", "ilusión", "ilusionado",
    "desesperación", "desesperado", "desesperanza",
    "gratitud", "agradecido", "agradecimiento",
    "culpa", "culpable", "remordimiento",
    "vergüenza", "avergonzado", "humillación",
    "orgullo", "orgulloso", "dignidad",
    "celos", "celoso", "envidia", "envidioso",
    "frustración", "frustrado", "decepción", "decepcionado",
    "estrés", "estresado", "agobio", "agobiado",
    "entusiasmo", "entusiasmado", "emoción", "emocionado",
    "pasión", "apasionado", "deseo", "anhelo",
    "soledad", "solo", "aislamiento", "aislado",
    "dolor", "sufrimiento", "angustia", "pena",
    "alivio", "aliviado", "consuelo", "consolado",
    "confianza", "seguridad", "inseguridad", "duda",
    "admiración", "admiración", "respeto",
    "ternura", "compasión", "empatía", "lástima",
    "indignación", "indignado", "impotencia",
    "aburrimiento", "aburrido", "hastío",
}

# English emotional keywords
_ENGLISH_EMOTIONAL: set[str] = {
    "happy", "happiness", "joy", "joyful", "glad",
    "sad", "sadness", "depressed", "depression", "unhappy",
    "angry", "anger", "furious", "rage", "mad",
    "afraid", "fear", "scared", "terrified", "panic",
    "surprised", "surprise", "amazed", "amazement",
    "love", "affection", "adore", "fondness",
    "hate", "hatred", "disgust", "despise",
    "anxiety", "anxious", "nervous", "worried", "worry",
    "calm", "peaceful", "serene", "peace", "serenity",
    "hope", "hopeful", "optimistic", "optimism",
    "despair", "desperate", "hopeless", "hopelessness",
    "gratitude", "grateful", "thankful", "thanks",
    "guilt", "guilty", "remorse", "shame", "ashamed",
    "pride", "proud", "dignity",
    "jealous", "jealousy", "envy", "envious",
    "frustration", "frustrated", "disappointment", "disappointed",
    "stress", "stressed", "overwhelmed",
    "excitement", "excited", "enthusiasm", "enthusiastic",
    "passion", "passionate", "desire", "longing",
    "loneliness", "lonely", "isolated", "isolation",
    "pain", "suffering", "anguish", "sorrow", "grief",
    "relief", "relieved", "comfort", "comforted",
    "confidence", "confident", "insecure", "doubt",
    "admiration", "respect", "awe",
    "compassion", "empathy", "pity", "tenderness",
    "indignation", "indignant", "outrage",
    "boredom", "bored", "tedium",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Remove combining diacritical marks (accents) from *text*."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _normalize_whitespace(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip."""
    return re.sub(r"\s+", " ", text).strip()


def _remove_fillers(text: str) -> str:
    """Remove common Spanish & English filler words / muletillas."""
    # Multi-word fillers first (longer matches before shorter)
    multi_word_fillers = sorted(
        [f for f in _SPANISH_FILLERS | _ENGLISH_FILLERS if " " in f],
        key=len, reverse=True,
    )
    single_word_fillers = sorted(
        [f for f in _SPANISH_FILLERS | _ENGLISH_FILLERS if " " not in f],
        key=len, reverse=True,
    )

    # Remove multi-word fillers as whole phrases (case-insensitive)
    for filler in multi_word_fillers:
        text = re.sub(
            r"\b" + re.escape(filler) + r"\b", "", text, flags=re.IGNORECASE
        )
    # Remove single-word fillers
    for filler in single_word_fillers:
        text = re.sub(
            r"\b" + re.escape(filler) + r"\b", "", text, flags=re.IGNORECASE
        )
    return _normalize_whitespace(text)


def _words(text: str) -> list[str]:
    """Return list of alphabetic word tokens (lowercase)."""
    return re.findall(r"[a-záéíóúüñ]+", text.lower())


def _proper_noun_candidates(text: str) -> list[str]:
    """Return mid-sentence capitalized words that look like proper nouns."""
    # Split into sentences roughly
    sentences = re.split(r"[.!?¿¡]+", text)
    candidates: list[str] = []
    for sentence in sentences:
        tokens = re.findall(r"\b[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+\b", sentence)
        # First token of a sentence is usually not a proper noun;
        # skip it, keep the rest.
        if tokens:
            candidates.extend(tokens[1:])
    return candidates


# ---------------------------------------------------------------------------
# TextPreprocessor
# ---------------------------------------------------------------------------

class TextPreprocessor:
    """Normalize, split, and estimate complexity of text.

    Every method works without an LLM; pass *llm_call* to upgrade quality.
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # 1. split_by_themes
    # ------------------------------------------------------------------

    def split_by_themes(
        self, text: str, llm_call: Optional[Callable[..., str]] = None
    ) -> list[dict[str, Any]]:
        """Split *text* into thematic segments.

        Parameters
        ----------
        text : str
            Raw input text.
        llm_call : callable or None
            If provided, a callable that accepts a prompt string and returns
            a JSON response with a ``"segments"`` list of
            ``{"theme": ..., "text": ...}``.

        Returns
        -------
        list[dict]
            Each dict has ``theme``, ``text``, ``start_char``, ``end_char``.
        """
        if llm_call is not None:
            return self._split_by_themes_llm(text, llm_call)
        return self._split_by_themes_heuristic(text)

    def _split_by_themes_llm(
        self, text: str, llm_call: Callable[..., str]
    ) -> list[dict[str, Any]]:
        prompt = (
            "You are a text segmentation assistant. Split the following text "
            "into thematic segments. Return a JSON object with a key "
            '"segments" that is a list of objects, each with "theme" (a short '
            'label like "introduction", "contrast", "conclusion", etc.) and '
            '"text" (the exact substring from the original text, unchanged).\n\n'
            f"Text:\n{text}\n\n"
            "Return ONLY valid JSON."
        )
        try:
            response = llm_call(prompt)
            import json

            data = json.loads(response)
            segments = data.get("segments", [])
        except Exception:
            # Graceful fallback to heuristic on any LLM failure
            return self._split_by_themes_heuristic(text)

        # Rebuild start_char / end_char by locating each segment text
        result: list[dict[str, Any]] = []
        cursor = 0
        for seg in segments:
            seg_text = seg.get("text", "")
            idx = text.find(seg_text, cursor)
            if idx == -1:
                idx = cursor  # fallback
            start = idx
            end = idx + len(seg_text)
            result.append(
                {
                    "theme": seg.get("theme", "general"),
                    "text": seg_text,
                    "start_char": start,
                    "end_char": end,
                }
            )
            cursor = end
        return result

    def _split_by_themes_heuristic(self, text: str) -> list[dict[str, Any]]:
        """Heuristic: blank lines, then topic markers, then sentence boundaries."""
        # 1. Split on blank lines (paragraphs)
        paragraphs = re.split(r"\n\s*\n", text)
        blocks: list[tuple[int, int]] = []
        cursor = 0
        for para in paragraphs:
            if not para.strip():
                cursor += len(para) + (2 if "\n" in text[cursor:] else 0)
                continue
            start = text.find(para, cursor)
            if start == -1:
                start = cursor
            end = start + len(para)
            blocks.append((start, end))
            cursor = end

        # 2. Within each block, try splitting on topic markers
        final_segments: list[dict[str, Any]] = []
        for b_start, b_end in blocks:
            sub_text = text[b_start:b_end]
            sub_segments = self._split_on_markers(sub_text, offset=b_start)
            if not sub_segments:
                # No markers found → keep as one segment
                theme = self._guess_theme(sub_text)
                final_segments.append(
                    {
                        "theme": theme,
                        "text": sub_text,
                        "start_char": b_start,
                        "end_char": b_end,
                    }
                )
            else:
                final_segments.extend(sub_segments)

        # 3. If few segments and text looks continuous (>1000 chars, <=2 blocks),
        #    try sentence-boundary splitting
        if len(final_segments) <= 2 and len(text) > 1000:
            final_segments = self._split_on_sentences(text)

        # 4. Force-split if still only 1 theme and text is long
        if len(final_segments) <= 1 and len(text) > 2000:
            final_segments = self._force_split_chunks(text, chunk_size=2000)

        return final_segments

    def _split_on_markers(
        self, text: str, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Split *text* on topic-transition markers, returning segments with
        absolute *offset* applied to char positions."""
        # Find all marker matches
        matches: list[tuple[int, int, str]] = []
        for pattern, theme in _TOPIC_MARKERS:
            for m in re.finditer(pattern, text):
                matches.append((m.start(), m.end(), theme))

        if not matches:
            return []

        # Sort by position
        matches.sort(key=lambda x: x[0])

        # Build segments: text before first marker is segment 0, etc.
        segments: list[dict[str, Any]] = []
        prev_end = 0
        for i, (m_start, m_end, theme) in enumerate(matches):
            # Text before this marker
            if m_start > prev_end:
                before = text[prev_end:m_start]
            else:
                before = ""

            if before.strip():
                # The previous segment's theme was set by the previous marker;
                # for the very first pre-marker text we guess.
                if i == 0:
                    g_theme = self._guess_theme(before)
                else:
                    # Use the *next* marker's theme (the one introducing this segment)
                    g_theme = theme
                segments.append(
                    {
                        "theme": g_theme,
                        "text": before,
                        "start_char": offset + prev_end,
                        "end_char": offset + m_start,
                    }
                )
            prev_end = m_end

        # Remaining text after last marker
        if prev_end < len(text):
            remainder = text[prev_end:]
            if remainder.strip():
                # The last marker's theme applies to the following text
                last_theme = matches[-1][2] if matches else "general"
                segments.append(
                    {
                        "theme": last_theme,
                        "text": remainder,
                        "start_char": offset + prev_end,
                        "end_char": offset + len(text),
                    }
                )

        return segments

    @staticmethod
    def _guess_theme(text: str) -> str:
        """Simple heuristic to guess theme from content."""
        lower = text.lower()
        if any(w in lower for w in ("conclusión", "conclusion", "en resumen", "finalmente")):
            return "conclusion"
        if any(w in lower for w in ("introducción", "introduction", "empecemos", "para empezar")):
            return "introduction"
        if any(w in lower for w in ("por ejemplo", "for example", "ejemplo")):
            return "example"
        if any(w in lower for w in ("sin embargo", "however", "no obstante", "pero")):
            return "contrast"
        if any(w in lower for w in ("porque", "debido a", "causa", "because", "therefore")):
            return "explanation"
        return "general"

    # ── Sentence-boundary splitting helpers ──────────────────────────

    def _split_on_sentences(self, text: str) -> list[dict[str, Any]]:
        """Split continuous text on sentence boundaries.

        For normal text: split on .!? + space + capital letter.
        For all-lowercase transcription text: split on connector words.
        Then group into theme groups of ~500-1000 chars.
        """
        # Detect if text is mostly lowercase (transcription-style)
        alpha_chars = sum(1 for c in text if c.isalpha())
        upper_chars = sum(1 for c in text if c.isupper())
        is_lowercase = (upper_chars / max(alpha_chars, 1)) < 0.05  # < 5% uppercase

        if is_lowercase:
            raw_sentences = self._split_lowercase_on_connectors(text)
        else:
            raw_sentences = self._split_on_punctuation(text)

        # Group sentences into theme groups of ~500-1000 chars
        groups = self._group_sentences(raw_sentences, min_size=500, max_size=1000)

        result: list[dict[str, Any]] = []
        cursor = 0
        for group_text in groups:
            idx = text.find(group_text, cursor)
            if idx == -1:
                idx = cursor  # fallback
            start = idx
            end = idx + len(group_text)
            result.append({
                "theme": self._guess_theme(group_text),
                "text": group_text,
                "start_char": start,
                "end_char": end,
            })
            cursor = end

        return result

    @staticmethod
    def _split_on_punctuation(text: str) -> list[str]:
        """Split text on sentence-ending punctuation (.!?) followed by space + capital."""
        parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ])', text)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _split_lowercase_on_connectors(text: str) -> list[str]:
        """Split all-lowercase text on connector words as pseudo-sentence boundaries."""
        # Build pattern from connectors, sorted by length (longest first)
        connectors_sorted = sorted(
            _TRANSCRIPTION_CONNECTORS, key=len, reverse=True
        )
        pattern = '|'.join(re.escape(c) for c in connectors_sorted)

        # Split on connector words, keeping them as part of the following segment
        parts = re.split(f'({pattern})', text)

        sentences: list[str] = []
        current = ""
        for part in parts:
            if part and re.match(f'^({pattern})$', part):
                # This is a connector — start a new sentence
                if current.strip():
                    sentences.append(current.strip())
                current = part
            else:
                current += part

        if current.strip():
            sentences.append(current.strip())

        # Further split any very long sentences (>1500 chars)
        result: list[str] = []
        for s in sentences:
            if len(s) > 1500:
                words = s.split()
                chunk = ""
                for w in words:
                    if len(chunk) + len(w) > 800:
                        if chunk:
                            result.append(chunk.strip())
                        chunk = w
                    else:
                        chunk += " " + w if chunk else w
                if chunk:
                    result.append(chunk.strip())
            else:
                result.append(s)

        return result

    @staticmethod
    def _group_sentences(
        sentences: list[str], min_size: int, max_size: int
    ) -> list[str]:
        """Group sentences into chunks of approximately min_size to max_size chars."""
        groups: list[str] = []
        current = ""
        for s in sentences:
            if current and len(current) + len(s) + 1 > max_size:
                groups.append(current)
                current = s
            else:
                if current:
                    current += " " + s
                else:
                    current = s

        if current:
            # If the last group is small, merge with previous
            if groups and len(current) < min_size:
                groups[-1] += " " + current
            else:
                groups.append(current)

        return groups

    @staticmethod
    def _force_split_chunks(
        text: str, chunk_size: int = 2000
    ) -> list[dict[str, Any]]:
        """Force-split text into chunks of approximately chunk_size chars."""
        result: list[dict[str, Any]] = []
        pos = 0
        while pos < len(text):
            end = min(pos + chunk_size, len(text))
            # Try to break at a space near the end
            if end < len(text):
                space_pos = text.rfind(' ', pos, end)
                if space_pos > pos + chunk_size // 2:
                    end = space_pos
            chunk = text[pos:end].strip()
            if chunk:
                theme = TextPreprocessor._guess_theme(chunk)
                result.append({
                    "theme": theme,
                    "text": chunk,
                    "start_char": pos,
                    "end_char": end,
                })
            pos = end
        return result

    # ------------------------------------------------------------------
    # 2. canonicalize
    # ------------------------------------------------------------------

    def canonicalize(
        self, text: str, llm_call: Optional[Callable[..., str]] = None
    ) -> str:
        """Normalize *text* to a canonical form for embedding matching.

        Parameters
        ----------
        text : str
            Raw input text.
        llm_call : callable or None
            If provided, used to generate a canonical sentence via LLM.

        Returns
        -------
        str
            Canonicalized text.
        """
        if llm_call is not None:
            return self._canonicalize_llm(text, llm_call)
        return self._canonicalize_heuristic(text)

    def _canonicalize_llm(
        self, text: str, llm_call: Callable[..., str]
    ) -> str:
        prompt = (
            "Rewrite the following text into a single, clear canonical "
            "sentence that preserves the core meaning. Remove filler words, "
            "hesitations, and redundancy. Return ONLY the canonical sentence, "
            "nothing else.\n\n"
            f"Text: {text}"
        )
        try:
            response = llm_call(prompt)
            return response.strip()
        except Exception:
            return self._canonicalize_heuristic(text)

    def _canonicalize_heuristic(self, text: str) -> str:
        """Basic normalization without an LLM."""
        # Lowercase
        out = text.lower()
        # Strip accents
        out = _strip_accents(out)
        # Remove filler words
        out = _remove_fillers(out)
        # Collapse whitespace
        out = _normalize_whitespace(out)
        # Remove punctuation that doesn't carry semantic weight
        out = re.sub(r"[^\w\s]", " ", out)
        out = _normalize_whitespace(out)
        return out

    # ------------------------------------------------------------------
    # 3. estimate_complexity
    # ------------------------------------------------------------------

    def estimate_complexity(
        self, text: str, entity_registry: Any = None
    ) -> dict[str, Any]:
        """Estimate textual complexity via simple heuristics.

        Parameters
        ----------
        text : str
            Raw input text.
        entity_registry : EntityRegistry or None
            If provided, used to cross-check entity names against the registry.

        Returns
        -------
        dict
            Keys: ``char_count`` (int), ``estimated_themes`` (int),
            ``emotional_density`` (float 0–1),
            ``entity_density`` (float 0–1).
        """
        char_count = len(text)

        # Estimated themes: count paragraphs (blank-line splits) + marker hints
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        marker_count = 0
        for pattern, _ in _TOPIC_MARKERS:
            marker_count += len(re.findall(pattern, text))
        estimated_themes = max(1, len(paragraphs) + marker_count)

        # Emotional density
        word_list = _words(text)
        total_words = len(word_list) or 1  # avoid div-by-zero
        emotional_count = sum(
            1 for w in word_list
            if w in _SPANISH_EMOTIONAL or w in _ENGLISH_EMOTIONAL
        )
        emotional_density = min(1.0, emotional_count / total_words)

        # Entity density — multiple strategies
        entity_count = 0

        # Strategy A: capitalized proper noun candidates (original heuristic)
        proper_candidates = _proper_noun_candidates(text)
        entity_count += len(proper_candidates)

        # Strategy B: for all-lowercase text, use Spanish preposition heuristic
        if entity_count == 0:
            entity_count += self._count_spanish_proper_nouns_heuristic(text)

        # Strategy C: cross-check with registry if available
        if entity_registry is not None:
            entity_count += self._count_registry_entities(text, entity_registry)

        entity_density = min(1.0, entity_count / total_words)

        return {
            "char_count": char_count,
            "estimated_themes": estimated_themes,
            "emotional_density": round(emotional_density, 4),
            "entity_density": round(entity_density, 4),
        }

    # ── Entity density helpers ─────────────────────────────────────

    @staticmethod
    def _count_spanish_proper_nouns_heuristic(text: str) -> int:
        """Count words after Spanish prepositions that look like proper names.

        In lowercase Spanish text, proper names often follow prepositions like
        'de', 'con', 'para', 'en'.  This heuristic counts the word immediately
        after those prepositions, excluding very common Spanish words.
        """
        # Common Spanish words to exclude (not proper nouns)
        _COMMON_SPANISH: set[str] = {
            "una", "un", "los", "las", "el", "la", "que", "eso", "ese",
            "esa", "todo", "toda", "todos", "todas", "muy", "más", "menos",
            "cada", "otro", "otra", "otros", "otras", "este", "esta",
            "mi", "tu", "su", "mis", "tus", "sus", "me", "te", "se",
            "le", "les", "lo", "nos", "hay", "era", "son",
            "fue", "han", "había", "ser", "estar", "puede", "hace",
            "tiene", "dice", "forma", "parte", "manera", "tipo", "modo",
            "caso", "lugar", "tiempo", "cosa", "cosas", "persona",
            "vida", "mundo", "día", "año", "gente", "país", "trabajo",
            "casa", "familia", "historia", "ejemplo", "razón", "hecho",
            "punto", "cuestión", "tema", "problema", "sistema",
            "porque", "cuando", "donde", "como", "entre", "hasta",
            "desde", "sobre", "sin", "contra", "hacia", "durante",
            "mucho", "poco", "bien", "mal", "mejor", "peor",
            "gran", "grande", "pequeño", "nuevo", "viejo",
            "bueno", "malo", "primero", "último", "mismo",
            "importante", "necesario", "posible", "capaz",
            "diferente", "único", "propio", "cierto", "tanto",
            "algún", "algunos", "ningún", "ninguno", "cualquier",
            "quiere", "pueden", "hacer", "tener", "decir", "saber",
            "ver", "dar", "ir", "venir", "llegar", "poner",
        }
        prepositions = {"de", "con", "para", "en"}
        count = 0
        words = text.lower().split()
        for i, word in enumerate(words):
            if word in prepositions and i + 1 < len(words):
                next_word = words[i + 1]
                if (
                    len(next_word) >= 3
                    and next_word.isalpha()
                    and next_word not in _COMMON_SPANISH
                ):
                    count += 1
        return count

    @staticmethod
    def _count_registry_entities(text: str, registry: Any) -> int:
        """Count how many known entity names from the registry appear in text."""
        count = 0
        lower_text = text.lower()
        try:
            # Try to get all active entity names
            entities = registry.db.execute(
                "SELECT canonical_name FROM entities WHERE status='active'"
            ).fetchall()
            for row in entities:
                name = row[0]
                if name.lower() in lower_text:
                    count += 1
            # Also check aliases
            aliases = registry.db.execute(
                "SELECT alias FROM aliases"
            ).fetchall()
            seen = set()
            for row in aliases:
                alias = row[0].lower()
                if alias not in seen and alias in lower_text:
                    seen.add(alias)
                    count += 1
        except Exception:
            pass  # registry unavailable or misconfigured
        return count
