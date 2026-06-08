import re
import difflib

class SpellingCorrector:
    def __init__(self, db_conn_fn):
        self.db_conn_fn = db_conn_fn
        self.vocab = {}
        self.vocab_words = []
        self.vocab_index = {}
        self.stop_words = {
            'with', 'and', 'for', 'the', 'tab', 'tabs', 'cap', 'caps', 'gel', 
            'syp', 'inj', 'tablet', 'tablets', 'capsule', 'capsules', 'syrup', 
            'injection', 'cream', 'ointment', 'suspension', 'solution', 'drop', 
            'drops', 'mg', 'ml', 'gm', 'mcg'
        }

    def load(self):
        print("SpellingCorrector: Loading vocabulary from database...")
        try:
            conn = self.db_conn_fn()
            try:
                cursor = conn.cursor(dictionary=True)
            except TypeError:
                cursor = conn.cursor()
            cursor.execute("SELECT name, salt_name FROM products")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"SpellingCorrector Error: Failed to fetch vocabulary from database: {e}")
            return

        # Build vocabulary from product names and salt names
        vocab_temp = {}
        for row in rows:
            text = ""
            if row.get('name'):
                text += " " + row['name']
            if row.get('salt_name'):
                text += " " + row['salt_name']
            
            # Match purely alphabetic words of length >= 3
            words = re.findall(r'[a-zA-Z]{3,}', text)
            for w in words:
                w_lower = w.lower()
                if w_lower not in self.stop_words:
                    vocab_temp[w_lower] = vocab_temp.get(w_lower, 0) + 1

        self.vocab = vocab_temp
        # Sort words by frequency (descending) so more common words are checked first
        sorted_vocab = sorted(vocab_temp.items(), key=lambda x: x[1], reverse=True)
        self.vocab_words = [w for w, freq in sorted_vocab]

        # Group words by first letter and length for fast lookup
        self.vocab_index = {}
        for w in self.vocab_words:
            first_char = w[0]
            l = len(w)
            if first_char not in self.vocab_index:
                self.vocab_index[first_char] = {}
            if l not in self.vocab_index[first_char]:
                self.vocab_index[first_char][l] = []
            self.vocab_index[first_char][l].append(w)

        print(f"SpellingCorrector: Vocabulary loaded. {len(self.vocab)} unique words indexed.")

    def correct(self, query):
        if not query:
            return query
            
        # Split query into alphanumeric words and other characters (delimiters, numbers, spaces)
        tokens = re.split(r'(\W+)', query)
        corrected_tokens = []
        
        for token in tokens:
            # Only correct purely alphabetic words of length >= 3
            if re.match(r'^[a-zA-Z]{3,}$', token):
                token_lower = token.lower()
                # If already valid word or stop word, keep it
                if token_lower in self.vocab or token_lower in self.stop_words:
                    corrected_tokens.append(token)
                else:
                    first_char = token_lower[0]
                    l_token = len(token_lower)
                    
                    # Gather candidates with the same first character and length +/- 2
                    candidates = []
                    if first_char in self.vocab_index:
                        for l in range(max(3, l_token - 2), l_token + 3):
                            candidates.extend(self.vocab_index[first_char].get(l, []))
                    
                    # Find closest match with a minimum similarity cutoff of 0.7
                    matches = difflib.get_close_matches(token_lower, candidates, n=1, cutoff=0.7)
                    if not matches:
                        # Fallback: search entire vocabulary with a slightly lower cutoff (0.6)
                        # to match misspelled first letter, insertions, or deletions.
                        matches = difflib.get_close_matches(token_lower, self.vocab_words, n=1, cutoff=0.6)
                        
                    if matches:
                        corrected = matches[0]
                        # Retain capitalization of original token if possible
                        if token.isupper():
                            corrected = corrected.upper()
                        elif token.istitle():
                            corrected = corrected.title()
                        corrected_tokens.append(corrected)
                    else:
                        corrected_tokens.append(token)
            else:
                corrected_tokens.append(token)
                
        return ''.join(corrected_tokens)
