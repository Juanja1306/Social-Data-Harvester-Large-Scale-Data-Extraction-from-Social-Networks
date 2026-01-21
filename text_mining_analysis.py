"""
Text Mining / NLP pipeline for `resultados.csv`

Requisitos (ver requirements.txt):
- pandas
- nltk
- scikit-learn
- wordcloud
- matplotlib

Qué hace:
1) Limpieza y normalización:
   - minúsculas
   - remueve URLs
   - remueve emojis/emoticones
   - remueve puntuación y caracteres no útiles
   - colapsa espacios
2) Tokenización
3) Remueve stopwords (ES + EN)
4) Stemming (Snowball: ES + EN)

Luego:
a) Bolsa de palabras (WordCloud + Top términos)
b) Otros análisis: bigramas + TF-IDF + LDA (temas)
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Iterable, List, Tuple

import pandas as pd

import matplotlib.pyplot as plt
from wordcloud import WordCloud

import nltk
from nltk.corpus import stopwords
from nltk.stem.snowball import SnowballStemmer

from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.decomposition import LatentDirichletAllocation


CSV_PATH = "resultados.csv"
OUTPUT_DIR = "nlp_outputs"


URL_RE = re.compile(r"(https?://\S+|www\.\S+)", flags=re.IGNORECASE)

# Emoji ranges (covers most emojis + symbols)
EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)

# Caracteres que queremos conservar como separadores
NON_TEXT_RE = re.compile(r"[^a-záéíóúñü0-9\s]", flags=re.IGNORECASE)
MULTISPACE_RE = re.compile(r"\s+")


def ensure_nltk_resources() -> None:
    """Descarga recursos NLTK si faltan (no interactivo)."""
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords", quiet=True)


def build_stopwords() -> set:
    """Stopwords español + inglés + extras para este dataset."""
    ensure_nltk_resources()
    sw = set(stopwords.words("spanish")) | set(stopwords.words("english"))

    # Extras típicos en social
    extras = {
        "https",
        "http",
        "www",
        "com",
        "reddit",
        "linkedin",
        "lnkd",
        "amp",
        "rt",
        "tco",
        "t",
        "r",
        "u",
        "us",
        "usa",
        "eeuu",
        "q",
        "a",
        "de",
        "la",
        "el",
        "y",
        "en",
        "un",
        "una",
        "para",
        "por",
        "con",
        "del",
        "al",
    }
    return sw | extras


def clean_text(text: str) -> str:
    """Limpieza y normalización base."""
    if not isinstance(text, str):
        return ""

    text = text.lower()
    text = URL_RE.sub(" ", text)
    text = EMOJI_RE.sub(" ", text)

    # Remover ruido común del UI / irrelevante (ajustable)
    noise_phrases = [
        "añadir un comentario",
        "abrir el teclado de emoji",
        "open emoji keyboard",
        "add a comment",
        "ver más",
        "see more",
    ]
    for p in noise_phrases:
        text = text.replace(p, " ")

    text = NON_TEXT_RE.sub(" ", text)
    text = MULTISPACE_RE.sub(" ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    """Tokenización simple (por espacios) después de clean_text."""
    if not text:
        return []
    return text.split()


def stem_tokens(tokens: Iterable[str]) -> List[str]:
    """Stemming híbrido ES/EN (elige stemmer según caracteres típicos)."""
    stem_es = SnowballStemmer("spanish")
    stem_en = SnowballStemmer("english")

    out: List[str] = []
    for tok in tokens:
        # Heurística: si contiene caracteres latinos típicos, usar ES; si no, EN
        if any(ch in tok for ch in ("á", "é", "í", "ó", "ú", "ñ", "ü")):
            out.append(stem_es.stem(tok))
        else:
            out.append(stem_en.stem(tok))
    return out


def preprocess_document(text: str, sw: set) -> List[str]:
    """Pipeline completo: clean -> tokenize -> stopwords -> stemming."""
    cleaned = clean_text(text)
    tokens = tokenize(cleaned)

    # Quitar tokens irrelevantes (cortos, solo dígitos, etc.)
    tokens = [
        t
        for t in tokens
        if len(t) >= 3 and not t.isdigit() and t not in sw
    ]

    tokens = stem_tokens(tokens)
    tokens = [t for t in tokens if t and t not in sw]
    return tokens


def load_corpus(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8")
    if "Data" not in df.columns:
        raise ValueError("El CSV no tiene columna 'Data'.")
    # IMPORTANTE: por requisito, SOLO se procesa la columna Data
    df["__text__"] = df["Data"].fillna("").astype(str)
    return df


def save_wordcloud(freq: Counter, output_path: str) -> None:
    wc = WordCloud(width=1600, height=900, background_color="white").generate_from_frequencies(freq)
    plt.figure(figsize=(14, 8))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def save_top_terms_bar(freq_items: List[Tuple[str, int]], output_path: str, title: str) -> None:
    terms = [t for t, _ in freq_items]
    counts = [c for _, c in freq_items]
    plt.figure(figsize=(12, 6))
    plt.barh(list(reversed(terms)), list(reversed(counts)))
    plt.title(title)
    plt.xlabel("Frecuencia")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def main() -> None:
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"No existe {CSV_PATH}.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = load_corpus(CSV_PATH)
    sw = build_stopwords()

    # Preprocesar documentos
    df["tokens"] = df["__text__"].apply(lambda t: preprocess_document(t, sw))
    df["processed_text"] = df["tokens"].apply(lambda toks: " ".join(toks))

    # ========= a) Bolsa de palabras =========
    all_tokens = [t for toks in df["tokens"] for t in toks]
    freq = Counter(all_tokens)

    save_wordcloud(freq, os.path.join(OUTPUT_DIR, "wordcloud.png"))

    top_30 = freq.most_common(30)
    save_top_terms_bar(top_30, os.path.join(OUTPUT_DIR, "top_terms.png"), "Top 30 términos (post-procesamiento)")

    # ========= b) Otros análisis =========
    # 1) Bigramas (frecuencia)
    cv_bi = CountVectorizer(ngram_range=(2, 2), min_df=2)
    X_bi = cv_bi.fit_transform(df["processed_text"])
    bi_terms = cv_bi.get_feature_names_out()
    bi_counts = X_bi.sum(axis=0).A1
    bi_top = sorted(zip(bi_terms, bi_counts), key=lambda x: x[1], reverse=True)[:20]
    save_top_terms_bar([(t, int(c)) for t, c in bi_top], os.path.join(OUTPUT_DIR, "top_bigrams.png"), "Top 20 bigramas")

    # 2) TF-IDF (términos más “importantes” promedio)
    tfidf = TfidfVectorizer(min_df=2)
    X_tfidf = tfidf.fit_transform(df["processed_text"])
    tfidf_terms = tfidf.get_feature_names_out()
    tfidf_mean = X_tfidf.mean(axis=0).A1
    tfidf_top = sorted(zip(tfidf_terms, tfidf_mean), key=lambda x: x[1], reverse=True)[:30]

    # Guardar top TF-IDF a TXT
    with open(os.path.join(OUTPUT_DIR, "top_tfidf_terms.txt"), "w", encoding="utf-8") as f:
        for term, score in tfidf_top:
            f.write(f"{term}\t{score:.6f}\n")

    # 3) LDA (temas) sobre bolsa de palabras
    cv = CountVectorizer(min_df=2)
    X = cv.fit_transform(df["processed_text"])
    vocab = cv.get_feature_names_out()

    n_topics = 5
    lda = LatentDirichletAllocation(
        n_components=n_topics,
        random_state=42,
        learning_method="batch",
        max_iter=20,
    )
    lda.fit(X)

    def top_words_for_topic(topic_idx: int, n: int = 10) -> List[str]:
        comp = lda.components_[topic_idx]
        top_idx = comp.argsort()[::-1][:n]
        return [vocab[i] for i in top_idx]

    with open(os.path.join(OUTPUT_DIR, "lda_topics.txt"), "w", encoding="utf-8") as f:
        for i in range(n_topics):
            words = top_words_for_topic(i, 12)
            f.write(f"TEMA {i+1}: " + ", ".join(words) + "\n")

    # También imprimimos un resumen corto
    print(f"[OK] Documentos leídos: {len(df)}")
    print(f"[OK] Tokens totales (post-procesamiento): {len(all_tokens)}")
    print(f"[OK] Outputs en: {OUTPUT_DIR}/")
    print("- wordcloud.png")
    print("- top_terms.png")
    print("- top_bigrams.png")
    print("- top_tfidf_terms.txt")
    print("- lda_topics.txt")


if __name__ == "__main__":
    main()

