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
        """Heuristic: blank lines, then topic markers."""
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

    def estimate_complexity(self, text: str) -> dict[str, Any]:
        """Estimate textual complexity via simple heuristics.

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

        # Entity density (proper noun heuristic)
        proper_candidates = _proper_noun_candidates(text)
        entity_density = min(1.0, len(proper_candidates) / total_words)

        return {
            "char_count": char_count,
            "estimated_themes": estimated_themes,
            "emotional_density": round(emotional_density, 4),
            "entity_density": round(entity_density, 4),
        }
