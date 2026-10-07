// Catálogos compartilhados com Python e identidade canônica do experimento.
package motor

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

type MetricPolicy struct {
	Direction           string  `json:"direction"`
	Transform           string  `json:"transform"`
	MaterialityAbsolute float64 `json:"materiality_absolute"`
	MaterialityRelative float64 `json:"materiality_relative"`
	SigmaFloor          float64 `json:"sigma_floor"`
}
type Fonte struct {
	CadenceSeconds    int    `json:"cadence_seconds"`
	IndependenceGroup string `json:"independence_group"`
}
type Regra struct {
	WindowMinutes int `json:"window_minutes"`
}
type Catalog struct {
	Sources map[string]Fonte
	Metrics struct {
		Exact    map[string]MetricPolicy `json:"exact"`
		Contains []struct {
			Token  string       `json:"token"`
			Policy MetricPolicy `json:"policy"`
		} `json:"contains"`
	}
	Relations struct {
		Aliases         map[string]string                 `json:"aliases"`
		StripSuffixes   []string                          `json:"strip_suffixes"`
		PrefixRelations []struct{ Parent, Prefix string } `json:"prefix_relations"`
	}
	Playback struct {
		Vhosts []string `json:"vhosts"`
	}
	Rules        map[string]Regra
	ManifestHash string
}

// CarregarCatalogo usa exatamente os cinco JSONs também carregados pelo Python.
func CarregarCatalogo(dir string) (*Catalog, error) {
	c := &Catalog{}
	raw := map[string]any{}
	for _, item := range []struct {
		name string
		dest any
	}{
		{"sources.json", &c.Sources}, {"metrics.json", &c.Metrics},
		{"entity_relations.json", &c.Relations}, {"playback.json", &c.Playback}, {"rules.json", &c.Rules},
	} {
		data, err := os.ReadFile(filepath.Join(dir, item.name))
		if err != nil {
			return nil, err
		}
		if err = json.Unmarshal(data, item.dest); err != nil {
			return nil, fmt.Errorf("%s: %w", item.name, err)
		}
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.UseNumber()
		var value any
		if err = decoder.Decode(&value); err != nil {
			return nil, err
		}
		raw[item.name] = value
	}
	if c.Sources["default"].CadenceSeconds <= 0 {
		return nil, fmt.Errorf("cadência padrão inválida")
	}
	for name, s := range c.Sources {
		if s.CadenceSeconds <= 0 {
			return nil, fmt.Errorf("cadência inválida: %s", name)
		}
	}
	c.ManifestHash = CanonicalHash(map[string]any{
		"catalogs": raw, "code_version": "local", "engine": "argus-rules-v1",
		"detector": map[string]any{
			"alpha": 0.20, "cold_start": 12, "z_threshold": 3.5,
			"strength_cap_z": 6.0, "timezone": "America/Sao_Paulo",
		},
		"scoring": map[string]any{
			"weights": map[string]any{
				"A": 0.25, "T": 0.20, "C": 0.20, "E": 0.15, "I": 0.15, "Q": 0.05,
			},
			"contradiction_penalty": 30,
		},
	})
	return c, nil
}
func (c *Catalog) Source(name string) Fonte {
	if v, ok := c.Sources[name]; ok {
		return v
	}
	return c.Sources["default"]
}
func (c *Catalog) Metric(name string) *MetricPolicy {
	if p, ok := c.Metrics.Exact[name]; ok {
		return &p
	}
	for _, item := range c.Metrics.Contains {
		if strings.Contains(strings.ToLower(name), item.Token) {
			return &item.Policy
		}
	}
	return nil
}

var entidadeRE = regexp.MustCompile(`[^a-z0-9]+`)

func (c *Catalog) NormalizeEntity(value string) string {
	n := strings.ToLower(strings.TrimSpace(value))
	if alias, ok := c.Relations.Aliases[n]; ok {
		return alias
	}
	for _, suffix := range c.Relations.StripSuffixes {
		if strings.HasSuffix(n, suffix) {
			n = strings.TrimSuffix(n, suffix)
			break
		}
	}
	n = strings.Trim(entidadeRE.ReplaceAllString(n, "-"), "-")
	if alias, ok := c.Relations.Aliases[n]; ok {
		return alias
	}
	return n
}
func (c *Catalog) Related(left, right string) bool {
	l, r := c.NormalizeEntity(left), c.NormalizeEntity(right)
	if l == r {
		return true
	}
	for _, relation := range c.Relations.PrefixRelations {
		if (l == relation.Parent && strings.HasPrefix(r, relation.Prefix)) || (r == relation.Parent && strings.HasPrefix(l, relation.Prefix)) {
			return true
		}
	}
	return false
}
func (c *Catalog) PlaybackVhost(entity string) bool {
	for _, v := range c.Playback.Vhosts {
		if strings.ToLower(entity) == v {
			return true
		}
	}
	return false
}

// CanonicalHash reproduz json.dumps(sort_keys=True, ensure_ascii=False) do Python.
// Os números do catálogo conservam o tipo lexical (6 e 6.0 são distintos no hash).
func CanonicalHash(value any) string {
	var b strings.Builder
	escreverCanonico(&b, value)
	digest := sha256.Sum256([]byte(b.String()))
	return hex.EncodeToString(digest[:])
}
func escreverString(b *strings.Builder, s string) {
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"', '\\':
			b.WriteByte('\\')
			b.WriteRune(r)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			if r < 32 {
				fmt.Fprintf(b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
}
func escreverCanonico(b *strings.Builder, value any) {
	switch v := value.(type) {
	case nil:
		b.WriteString("null")
	case string:
		escreverString(b, v)
	case bool:
		b.WriteString(strconv.FormatBool(v))
	case int:
		b.WriteString(strconv.Itoa(v))
	case int64:
		b.WriteString(strconv.FormatInt(v, 10))
	case json.Number:
		if strings.ContainsAny(string(v), ".eE") {
			f, err := v.Float64()
			if err != nil {
				panic(err)
			}
			escreverCanonico(b, f)
		} else {
			b.WriteString(string(v))
		}
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) {
			panic("número não finito em identidade canônica")
		}
		format := byte('f')
		a := math.Abs(v)
		if a != 0 && (a < 1e-4 || a >= 1e16) {
			format = 'e'
		}
		s := strconv.FormatFloat(v, format, -1, 64)
		if !strings.ContainsAny(s, ".e") {
			s += ".0"
		}
		b.WriteString(s)
	case []string:
		b.WriteByte('[')
		for i, s := range v {
			if i > 0 {
				b.WriteByte(',')
			}
			escreverString(b, s)
		}
		b.WriteByte(']')
	case []any:
		b.WriteByte('[')
		for i, s := range v {
			if i > 0 {
				b.WriteByte(',')
			}
			escreverCanonico(b, s)
		}
		b.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(v))
		for k := range v {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		b.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				b.WriteByte(',')
			}
			escreverString(b, k)
			b.WriteByte(':')
			escreverCanonico(b, v[k])
		}
		b.WriteByte('}')
	default:
		panic(fmt.Sprintf("tipo canônico não suportado: %T", v))
	}
}
