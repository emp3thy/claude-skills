package build

type Config struct {
	Name string
	Port int
	TLS  bool
}

type Builder struct {
	cfg Config
}

func NewConfig() *Builder { return &Builder{} }

func (b *Builder) WithName(name string) *Builder { b.cfg.Name = name; return b }
func (b *Builder) WithPort(port int) *Builder    { b.cfg.Port = port; return b }
func (b *Builder) WithTLS(on bool) *Builder      { b.cfg.TLS = on; return b }
func (b *Builder) Build() Config                 { return b.cfg }
