"""Language registry — maps file extensions to tree-sitter grammars, queries, and thresholds.

Each language entry defines everything needed to parse and measure code in that
language: which tree-sitter grammar to load, what AST queries to run, what node
type names to look for, and what thresholds to apply.

Adding a new language:
  1. `uv add tree-sitter-<lang>`  (install the PyPI package)
  2. Add an entry to LANGUAGES dict below
  3. Write tree-sitter queries for functions, calls, imports
  4. Set appropriate thresholds

The queries use capture names (@func, @name, @params) that are language-agnostic
even though the AST node types differ.
"""

from __future__ import annotations

from typing import Any

from tree_sitter import Language, Parser, Query

# ── Type aliases ────────────────────────────────────────────────────────

LanguageDef = dict[str, Any]


def _make_parser(import_path: str, lang_attr: str = "language") -> Parser:
    """Dynamically import a tree-sitter language package and create a parser."""
    import importlib

    mod = importlib.import_module(import_path)
    lang_fn = getattr(mod, lang_attr)
    lang = Language(lang_fn())
    parser = Parser()
    parser.language = lang
    return parser


# ── Language definitions ────────────────────────────────────────────────

LANGUAGES: dict[str, LanguageDef] = {}


def _register(name: str, defn: LanguageDef) -> None:
    defn["name"] = name
    LANGUAGES[name] = defn


# ── Python ───────────────────────────────────────────────────────────────

_register(
    "python",
    {
        "extensions": [".py"],
        "import_path": "tree_sitter_python",
        "lang_attr": "language",
        "thresholds": {
            "parameter_count": 6,
            "nesting_depth": 4,
            "function_length": 60,
            "cyclomatic_complexity": 10,
            "cognitive_complexity": 15,
            "boolean_complexity": 3,
            "god_class_methods": 10,
            "god_class_deps": 6,
            "god_class_lines": 100,
        },
        "queries": {
            "functions": """
            (function_definition
              name: (identifier) @name
              parameters: (parameters) @params) @func
        """,
            "calls": """
            (call function: (identifier) @name) @call
            (call function: (attribute attribute: (identifier) @name)) @call
        """,
            "imports": """
            (import_statement name: (dotted_name) @name)
            (import_from_statement module_name: (dotted_name) @name)
        """,
            "classes": """
            (class_definition
              name: (identifier) @name
              body: (block) @body) @class
        """,
        },
        "ignore_names": [],
        # Node types that count as +1 to cyclomatic complexity
        "decision_types": [
            "if_statement",
            "elif_clause",
            "for_statement",
            "while_statement",
            "except_clause",
            "boolean_operator",
        ],
        # Node types inside conditions that represent boolean operators
        "boolean_operator_types": ["and", "or"],
        "entry_points": [
            "main",
            "setup",
            "run",
            "start",
            "app",
            "create_app",
            "get_app",
            "handler",
        ],
        "risky_call_targets": [
            # File I/O
            "open",
            "io.open",
            "os.open",
            "os.read",
            "os.write",
            "os.remove",
            "os.unlink",
            "os.rename",
            "os.replace",
            "os.mkdir",
            "os.makedirs",
            "os.rmdir",
            "os.removedirs",
            "os.scandir",
            "os.listdir",
            "os.walk",
            "shutil.copy",
            "shutil.copy2",
            "shutil.copytree",
            "shutil.move",
            "shutil.rmtree",
            "shutil.make_archive",
            "pathlib.Path.write_text",
            "pathlib.Path.write_bytes",
            "pathlib.Path.read_text",
            "pathlib.Path.read_bytes",
            "tempfile.mkstemp",
            "tempfile.mkdtemp",
            "tempfile.mktemp",
            # Network / HTTP
            "connect",
            "request",
            "fetch",
            "send",
            "recv",
            "socket.socket",
            "socket.connect",
            "socket.send",
            "socket.recv",
            "requests.get",
            "requests.post",
            "requests.put",
            "requests.delete",
            "requests.request",
            "httpx.get",
            "httpx.post",
            "httpx.put",
            "httpx.delete",
            "urllib.request.urlopen",
            "urllib.request.urlretrieve",
            "aiohttp.ClientSession",
            "aiohttp.ClientSession.get",
            "aiohttp.ClientSession.post",
            # Database
            "execute",
            "query",
            "executemany",
            "executescript",
            "cursor.execute",
            "cursor.executemany",
            "session.query",
            "session.execute",
            "session.commit",
            "session.flush",
            "session.refresh",
            "session.merge",
            "db.session.execute",
            "db.session.commit",
            "sqlite3.connect",
            "sqlite3.execute",
            # Serialization / parsing
            "json.loads",
            "json.dumps",
            "json.load",
            "json.dump",
            "pickle.loads",
            "pickle.dumps",
            "pickle.load",
            "pickle.dump",
            "yaml.load",
            "yaml.safe_load",
            "yaml.dump",
            "yaml.dump_all",
            "toml.load",
            "toml.loads",
            "configparser.read",
            # Subprocess / OS commands
            "subprocess.run",
            "subprocess.call",
            "subprocess.Popen",
            "subprocess.check_call",
            "subprocess.check_output",
            "os.system",
            "os.popen",
            "os.execl",
            "os.execle",
            "os.execlp",
            "os.execv",
            "os.execve",
            "os.execvp",
            "os.execvpe",
            "os.fork",
            "os.forkpty",
            # Code evaluation / dynamic
            "eval",
            "exec",
            "compile",
            "__import__",
            "importlib.import_module",
            "importlib.reload",
            # Reflection / FFI
            "ctypes.CDLL",
            "ctypes.CDLL.load",
            "ctypes.WinDLL",
            "ctypes.CFUNCTYPE",
            "ctypes.PYFUNCTYPE",
            # Memory / low-level
            "mmap.mmap",
            "mmap.write",
            "mmap.read",
            # Logging (side effect, not risky per se, but counts as I/O)
            "logging.basicConfig",
            "logging.FileHandler",
            "logging.StreamHandler",
        ],
        "impure_call_targets": [
            # I/O that breaks purity
            "print",
            "input",
            "open",
            "read",
            "write",
            "random.random",
            "random.randint",
            "random.choice",
            "random.shuffle",
            "random.sample",
            "random.uniform",
            "secrets.token_bytes",
            "secrets.token_hex",
            "secrets.choice",
            "time.time",
            "time.sleep",
            "time.gmtime",
            "time.localtime",
            "time.monotonic",
            "time.perf_counter",
            "datetime.now",
            "datetime.utcnow",
            "datetime.today",
            "datetime.datetime.now",
            "datetime.datetime.utcnow",
            "os.environ",
            "os.getenv",
            "os.putenv",
            "os.environ.get",
            "sys.stdout.write",
            "sys.stderr.write",
            "sys.stdin.read",
            "sys.argv",
            "logging",
            "log",
            "logger.info",
            "logger.error",
            "logger.warning",
            "logger.debug",
            "logger.critical",
            "subprocess",
            "os.system",
            "os.popen",
            "uuid.uuid4",
            "uuid.uuid1",
            "hashlib.md5",
            "hashlib.sha256",
        ],
    },
)

# ── JavaScript ───────────────────────────────────────────────────────────

_register(
    "javascript",
    {
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
        "import_path": "tree_sitter_javascript",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": """
            (function_declaration
              name: (identifier) @name
              parameters: (formal_parameters) @params) @func
            (arrow_function
              parameters: (formal_parameters) @params) @func
            (method_definition
              name: (property_identifier) @name
              parameters: (formal_parameters) @params) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (member_expression
              property: (property_identifier) @name)) @call
        """,
            "imports": """
            (import_statement source: (string) @name)
        """,
            "classes": """
            (class_declaration
              name: (identifier) @name
              body: (class_body) @body) @class
        """,
            "exports": """
            (export_statement
              (function_declaration name: (identifier) @name))
            (export_statement
              (lexical_declaration
                (variable_declarator name: (identifier) @name)))
            (export_statement
              (class_declaration name: (identifier) @name))
            (export_statement
              (export_clause
                (export_specifier name: (identifier) @name)))
        """,
        },
        "ignore_names": ["constructor"],
        "entry_points": [
            "main",
            "handler",
            "render",
            "createApp",
            "getServerSideProps",
            "getStaticProps",
            "getInitialProps",
            "middleware",
        ],
        "risky_call_targets": [
            "fetch",
            "XMLHttpRequest",
            "axios.get",
            "axios.post",
            "axios.put",
            "axios.delete",
            "axios.request",
            "$.ajax",
            "$.get",
            "$.post",
            "localStorage.getItem",
            "localStorage.setItem",
            "localStorage.removeItem",
            "sessionStorage.getItem",
            "sessionStorage.setItem",
            "sessionStorage.removeItem",
            "document.cookie",
            "open",
            "write",
            "read",
            "WebSocket",
            "WebSocket.send",
            "console.log",
            "console.error",
            "console.warn",
            "process.exit",
            "process.cwd",
            "process.env",
            "fs.readFile",
            "fs.writeFile",
            "fs.readFileSync",
            "fs.writeFileSync",
            "fs.appendFile",
            "fs.unlink",
            "fs.mkdir",
            "fs.rmdir",
            "fs.readdir",
            "fs.createReadStream",
            "fs.createWriteStream",
            "JSON.parse",
            "JSON.stringify",
            "crypto.randomBytes",
            "crypto.randomUUID",
            "crypto.createHash",
            "crypto.createHmac",
            "child_process.exec",
            "child_process.spawn",
            "child_process.fork",
            "child_process.execSync",
            "eval",
            "Function",
            "setTimeout",
            "setInterval",
        ],
        "impure_call_targets": [
            "Math.random",
            "Date.now",
            "Date",
            "console.log",
            "console.error",
            "console.warn",
            "console.info",
            "process.env",
            "process.argv",
            "process.exit",
            "fetch",
            "XMLHttpRequest",
            "localStorage",
            "sessionStorage",
            "Math.floor(Math.random",
            "crypto.randomUUID",
        ],
    },
)

# ── TypeScript ───────────────────────────────────────────────────────────

_register(
    "typescript",
    {
        "extensions": [".ts", ".tsx", ".mts", ".cts"],
        "import_path": "tree_sitter_typescript",
        "lang_attr": "language_typescript",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": """
            (function_declaration
              name: (identifier) @name
              parameters: (formal_parameters) @params) @func
            (arrow_function
              parameters: (formal_parameters) @params) @func
            (method_definition
              name: (property_identifier) @name
              parameters: (formal_parameters) @params) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (member_expression
              property: (property_identifier) @name)) @call
        """,
            "imports": """
            (import_statement source: (string) @name)
        """,
            "classes": """
            (class_declaration
              name: (identifier) @name
              body: (class_body) @body) @class
        """,
            "exports": """
            (export_statement
              (function_declaration name: (identifier) @name))
            (export_statement
              (lexical_declaration
                (variable_declarator name: (identifier) @name)))
            (export_statement
              (class_declaration name: (identifier) @name))
            (export_statement
              (export_clause
                (export_specifier name: (identifier) @name)))
        """,
        },
        "ignore_names": ["constructor"],
        "entry_points": [
            "main",
            "handler",
            "render",
            "createApp",
            "getServerSideProps",
            "getStaticProps",
            "getInitialProps",
            "middleware",
        ],
        "risky_call_targets": [
            "fetch",
            "XMLHttpRequest",
            "axios.get",
            "axios.post",
            "axios.put",
            "axios.delete",
            "axios.request",
            "$.ajax",
            "$.get",
            "$.post",
            "localStorage.getItem",
            "localStorage.setItem",
            "localStorage.removeItem",
            "sessionStorage.getItem",
            "sessionStorage.setItem",
            "sessionStorage.removeItem",
            "document.cookie",
            "open",
            "write",
            "read",
            "WebSocket",
            "WebSocket.send",
            "console.log",
            "console.error",
            "console.warn",
            "process.exit",
            "process.cwd",
            "process.env",
            "fs.readFile",
            "fs.writeFile",
            "fs.readFileSync",
            "fs.writeFileSync",
            "fs.appendFile",
            "fs.unlink",
            "fs.mkdir",
            "fs.rmdir",
            "fs.readdir",
            "fs.createReadStream",
            "fs.createWriteStream",
            "JSON.parse",
            "JSON.stringify",
            "crypto.randomBytes",
            "crypto.randomUUID",
            "crypto.createHash",
            "crypto.createHmac",
            "child_process.exec",
            "child_process.spawn",
            "child_process.fork",
            "child_process.execSync",
            "eval",
            "Function",
            "setTimeout",
            "setInterval",
        ],
        "impure_call_targets": [
            "Math.random",
            "Date.now",
            "Date",
            "console.log",
            "console.error",
            "console.warn",
            "console.info",
            "process.env",
            "process.argv",
            "process.exit",
            "fetch",
            "XMLHttpRequest",
            "localStorage",
            "sessionStorage",
            "Math.floor(Math.random",
            "crypto.randomUUID",
        ],
    },
)

# ── Go ───────────────────────────────────────────────────────────────────

_register(
    "go",
    {
        "extensions": [".go"],
        "import_path": "tree_sitter_go",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": """
            (function_declaration
              name: (identifier) @name
              parameters: (parameter_list) @params) @func
            (method_declaration
              name: (field_identifier) @name
              parameters: (parameter_list) @params) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (selector_expression field: (field_identifier) @name)) @call
        """,
            "imports": """
            (import_spec (interpreted_string_literal) @name)
        """,
        },
        "ignore_names": ["init", "main"],
        "entry_points": ["main", "init", "Handler", "ServeHTTP", "Run", "Start"],
        "risky_call_targets": [
            "os.Open",
            "os.Create",
            "os.ReadFile",
            "os.WriteFile",
            "ioutil.ReadFile",
            "ioutil.WriteFile",
            "ioutil.ReadAll",
            "net.Dial",
            "net.DialTCP",
            "net.DialUDP",
            "net.Listen",
            "net.ListenTCP",
            "net.ListenUDP",
            "http.Get",
            "http.Post",
            "http.PostForm",
            "http.Do",
            "http.ListenAndServe",
            "http.ListenAndServeTLS",
            "exec.Command",
            "exec.CommandContext",
            "os/exec.Command",
            "os/exec.CommandContext",
            "syscall.Open",
            "syscall.Read",
            "syscall.Write",
            "syscall.Exec",
            "syscall.ForkExec",
            "database/sql.Open",
            "database/sql.DB.Query",
            "database/sql.DB.Exec",
            "database/sql.DB.Begin",
            "encoding/json.Unmarshal",
            "encoding/json.Marshal",
            "encoding/json.Decode",
            "encoding/json.NewDecoder",
            "crypto/rand.Read",
            "crypto/rand.Int",
            "fmt.Print",
            "fmt.Printf",
            "fmt.Println",
            "fmt.Fprint",
            "log.Print",
            "log.Printf",
            "log.Println",
            "log.Fatal",
        ],
        "impure_call_targets": [
            "fmt.Print",
            "fmt.Printf",
            "fmt.Println",
            "fmt.Fprint",
            "log.Print",
            "log.Printf",
            "log.Println",
            "log.Fatal",
            "os.Stdout",
            "os.Stderr",
            "os.Stdin",
            "os.Getenv",
            "os.Setenv",
            "os.Getpid",
            "os.Hostname",
            "time.Now",
            "time.Sleep",
            "time.After",
            "math/rand.Int",
            "math/rand.Intn",
            "math/rand.Float64",
            "crypto/rand.Read",
            "crypto/rand.Int",
            "net/http.Get",
            "net/http.Post",
            "net/http.Do",
        ],
    },
)

# ── Rust ─────────────────────────────────────────────────────────────────

_register(
    "rust",
    {
        "extensions": [".rs"],
        "import_path": "tree_sitter_rust",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 60},
        "queries": {
            "functions": """
            (function_item
              name: (identifier) @name
              parameters: (parameters) @params) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (scoped_identifier name: (identifier) @name)) @call
            (call_expression function: (field_expression field: (field_identifier) @name)) @call
        """,
            "imports": """
            (use_declaration (scoped_identifier (identifier) @name))
            (use_declaration (use_list (identifier) @name))
        """,
        },
        "ignore_names": ["main"],
        "entry_points": ["main", "run", "start", "init"],
        "risky_call_targets": [
            "std::fs::File::open",
            "std::fs::File::create",
            "std::fs::read",
            "std::fs::write",
            "std::fs::read_to_string",
            "std::fs::remove_file",
            "std::fs::remove_dir_all",
            "std::fs::create_dir",
            "std::fs::create_dir_all",
            "std::net::TcpStream::connect",
            "std::net::TcpListener::bind",
            "std::net::UdpSocket::bind",
            "reqwest::get",
            "reqwest::Client::get",
            "reqwest::Client::post",
            "reqwest::Client::put",
            "reqwest::Client::delete",
            "std::process::Command::new",
            "std::process::Command::output",
            "std::process::Command::spawn",
            "std::process::exit",
            "std::io::stdin",
            "std::io::stdout",
            "std::io::stderr",
            "std::io::BufReader::new",
            "std::io::BufWriter::new",
            "serde_json::from_str",
            "serde_json::to_string",
            "serde_json::from_reader",
            "serde_json::to_writer",
            "rand::random",
            "rand::thread_rng",
            "chrono::Utc::now",
            "chrono::Local::now",
            "log::info",
            "log::error",
            "log::warn",
            "log::debug",
        ],
        "impure_call_targets": [
            "println",
            "print",
            "eprint",
            "eprintln",
            "std::io::stdout",
            "std::io::stderr",
            "std::io::stdin",
            "log::info",
            "log::error",
            "log::warn",
            "log::debug",
            "rand::random",
            "rand::thread_rng",
            "std::time::SystemTime::now",
            "std::time::Instant::now",
            "chrono::Utc::now",
            "chrono::Local::now",
            "std::env::var",
            "std::env::args",
            "std::process::exit",
        ],
    },
)

# ── Java ─────────────────────────────────────────────────────────────────

_register(
    "java",
    {
        "extensions": [".java"],
        "import_path": "tree_sitter_java",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": (
                "(method_declaration name: (identifier) @name"
                " parameters: (formal_parameters) @params) @func"
            ),
            "calls": "(method_invocation name: (identifier) @name) @call",
            "imports": "(import_declaration (scoped_identifier (identifier) @name))",
        },
        "classes": """
            (class_declaration
              name: (identifier) @name
              body: (class_body) @body) @class
        """,
        "ignore_names": [],
        "entry_points": ["main", "run", "start", "handler", "handle"],
        "risky_call_targets": [
            "java.io.File",
            "java.io.FileReader",
            "java.io.FileWriter",
            "java.io.BufferedReader",
            "java.io.BufferedWriter",
            "java.nio.file.Files.read",
            "java.nio.file.Files.write",
            "java.nio.file.Files.copy",
            "java.nio.file.Files.move",
            "java.nio.file.Files.delete",
            "java.nio.file.Files.createDirectory",
            "java.net.Socket",
            "java.net.ServerSocket",
            "java.net.URL.openConnection",
            "java.net.URL.openStream",
            "java.net.HttpURLConnection",
            "okhttp3.OkHttpClient",
            "okhttp3.Request",
            "java.sql.Connection",
            "java.sql.Statement.executeQuery",
            "java.sql.Statement.executeUpdate",
            "java.sql.PreparedStatement.executeQuery",
            "java.lang.Runtime.exec",
            "java.lang.ProcessBuilder",
            "java.lang.Runtime.getRuntime",
            "java.beans.XMLDecoder",
            "java.beans.XMLEncoder",
            "javax.script.ScriptEngineManager",
            "java.io.ObjectInputStream",
            "java.io.ObjectOutputStream",
            "java.util.logging.Logger.info",
            "java.util.logging.Logger.warning",
            "java.lang.System.out.println",
            "java.lang.System.err.println",
            "java.lang.System.exit",
            "javax.xml.parsers.DocumentBuilderFactory.parse",
            "javax.xml.transform.TransformerFactory.transform",
        ],
        "impure_call_targets": [
            "java.lang.System.out.println",
            "java.lang.System.err.println",
            "java.lang.System.currentTimeMillis",
            "java.lang.System.nanoTime",
            "java.lang.System.getenv",
            "java.lang.System.getProperty",
            "java.lang.System.exit",
            "java.time.Clock.systemUTC",
            "java.time.Instant.now",
            "java.util.Random.nextInt",
            "java.util.Random.nextDouble",
            "java.security.SecureRandom.next",
            "java.util.logging.Logger",
        ],
    },
)

# ── Ruby ─────────────────────────────────────────────────────────────────

_register(
    "ruby",
    {
        "extensions": [".rb", ".rake", ".gemspec"],
        "import_path": "tree_sitter_ruby",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 40},
        "queries": {
            "functions": (
                "(method name: (identifier) @name parameters: (method_parameters) @params) @func"
            ),
            "calls": "(call method: (identifier) @name) @call",
            "imports": "(call method: (identifier) @name)",
        },
        "classes": """
            (class
              name: (constant) @name
              body: (body_statement) @body) @class
        """,
        "ignore_names": ["initialize"],
        "entry_points": ["main", "run", "start", "handler", "call"],
        "risky_call_targets": [
            "File.open",
            "File.read",
            "File.write",
            "File.rename",
            "File.delete",
            "FileUtils.cp",
            "FileUtils.mv",
            "FileUtils.rm",
            "Dir.mkdir",
            "Dir.rmdir",
            "Dir.entries",
            "Net::HTTP.get",
            "Net::HTTP.post",
            "Net::HTTP.start",
            "Net::HTTP.get_response",
            "Net::HTTP.post_form",
            "URI.open",
            "URI.parse",
            "open-uri",
            "OpenURI.open_uri",
            "JSON.parse",
            "JSON.generate",
            "JSON.load",
            "JSON.dump",
            "YAML.load",
            "YAML.safe_load",
            "YAML.dump",
            "Psych.load",
            "Psych.safe_load",
            "Psych.dump",
            "IO.read",
            "IO.write",
            "IO.binread",
            "IO.binwrite",
            "open",
            "system",
            "exec",
            "spawn",
            "popen",
            "\x60command\x60",
            "%x()",
            "eval",
            "class_eval",
            "instance_eval",
            "module_eval",
            "binding",
            "Kernel#system",
            "Kernel#exec",
            "Kernel#spawn",
            "Thread.new",
            "Fiber.new",
            "Logger.new",
            "Rails.logger",
        ],
        "impure_call_targets": [
            "puts",
            "print",
            "p",
            "pp",
            "Kernel#puts",
            "Kernel#print",
            "Kernel#p",
            "Random.rand",
            "Random.new",
            "srand",
            "Time.now",
            "Time.new",
            "DateTime.now",
            "ENV",
            "ENV[]",
            "ARGV",
            "$stdin",
            "$stdout",
            "$stderr",
            "logger",
            "Rails.logger",
        ],
    },
)

# ── PHP ──────────────────────────────────────────────────────────────────

_register(
    "php",
    {
        "extensions": [".php"],
        "import_path": "tree_sitter_php",
        "lang_attr": "language_php",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": (
                "(function_definition name: (name) @name"
                " parameters: (formal_parameters) @params) @func"
            ),
            "calls": """
            (function_call_expression (name) @name) @call
            (member_call_expression (name) @name) @call
        """,
            "imports": "(namespace_use_clause (qualified_name (name) @name))",
        },
        "classes": """
            (class_declaration
              name: (name) @name
              body: (declaration_list) @body) @class
        """,
        "ignore_names": ["__construct"],
        "entry_points": ["main", "run", "start", "handler", "handle"],
        "risky_call_targets": [
            "fopen",
            "fread",
            "fwrite",
            "fclose",
            "file_get_contents",
            "file_put_contents",
            "unlink",
            "rename",
            "copy",
            "move_uploaded_file",
            "mkdir",
            "rmdir",
            "scandir",
            "glob",
            "fsockopen",
            "pfsockopen",
            "stream_socket_client",
            "stream_socket_server",
            "curl_init",
            "curl_exec",
            "curl_setopt",
            "json_decode",
            "json_encode",
            "unserialize",
            "serialize",
            "simplexml_load_string",
            "simplexml_load_file",
            "mysqli_query",
            "mysqli_execute",
            "PDO::query",
            "PDO::exec",
            "exec",
            "system",
            "passthru",
            "shell_exec",
            "popen",
            "proc_open",
            "eval",
            "assert",
            "create_function",
            "preg_replace",
            "mail",
            "error_log",
            "syslog",
            "session_start",
            "session_destroy",
            "header",
            "setcookie",
        ],
        "impure_call_targets": [
            "echo",
            "print",
            "printf",
            "var_dump",
            "print_r",
            "rand",
            "mt_rand",
            "random_int",
            "time",
            "microtime",
            "date",
            "DateTime",
            "error_log",
            "trigger_error",
            "session_start",
        ],
    },
)

# ── C ────────────────────────────────────────────────────────────────────

_register(
    "c",
    {
        "extensions": [".c", ".h"],
        "import_path": "tree_sitter_c",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 6, "nesting_depth": 4, "function_length": 40},
        "queries": {
            "functions": """
            (function_definition
              declarator: (function_declarator
                declarator: (identifier) @name
                parameters: (parameter_list) @params)) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
        """,
            "imports": """
            (preproc_include path: (string_literal) @name)
            (preproc_include path: (system_lib_string) @name)
        """,
        },
        "ignore_names": ["main"],
        "entry_points": ["main"],
        "risky_call_targets": [
            "fopen",
            "fread",
            "fwrite",
            "fclose",
            "fprintf",
            "fscanf",
            "remove",
            "rename",
            "mkfifo",
            "mktemp",
            "system",
            "popen",
            "execv",
            "execvp",
            "fork",
            "socket",
            "connect",
            "bind",
            "listen",
            "accept",
            "send",
            "recv",
            "open",
            "read",
            "write",
            "close",
            "creat",
            "unlink",
            "stat",
            "lstat",
            "fstat",
            "access",
            "dlopen",
            "dlsym",
            "signal",
            "sigaction",
            "kill",
            "printf",
            "fprintf",
            "sprintf",
            "snprintf",
            "scanf",
            "fscanf",
            "sscanf",
            "syslog",
            "openlog",
        ],
        "impure_call_targets": [
            "printf",
            "fprintf",
            "dprintf",
            "puts",
            "putchar",
            "scanf",
            "fscanf",
            "getchar",
            "gets",
            "time",
            "clock",
            "gettimeofday",
            "rand",
            "srand",
            "random",
            "signal",
            "raise",
        ],
    },
)

# ── C++ ──────────────────────────────────────────────────────────────────

_register(
    "cpp",
    {
        "extensions": [".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx"],
        "import_path": "tree_sitter_cpp",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 6, "nesting_depth": 4, "function_length": 40},
        "queries": {
            "functions": """
            (function_definition
              declarator: (function_declarator
                declarator: (identifier) @name
                parameters: (parameter_list) @params)) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (field_expression field: (field_identifier) @name)) @call
        """,
            "imports": """
            (preproc_include path: (string_literal) @name)
            (preproc_include path: (system_lib_string) @name)
        """,
        },
        "classes": """
            (class_specifier
              name: (type_identifier) @name
              body: (field_declaration_list) @body) @class
        """,
        "ignore_names": ["main"],
        "entry_points": ["main"],
        "risky_call_targets": [
            "fopen",
            "fread",
            "fwrite",
            "fclose",
            "fprintf",
            "fscanf",
            "remove",
            "rename",
            "mkdir",
            "rmdir",
            "tmpfile",
            "tmpnam",
            "system",
            "popen",
            "execv",
            "execvp",
            "fork",
            "socket",
            "connect",
            "bind",
            "listen",
            "accept",
            "send",
            "recv",
            "open",
            "read",
            "write",
            "close",
            "creat",
            "unlink",
            "stat",
            "lstat",
            "fstat",
            "access",
            "dlopen",
            "dlsym",
            "setenv",
            "getenv",
            "putenv",
            "signal",
            "sigaction",
            "kill",
            "printf",
            "fprintf",
            "sprintf",
            "snprintf",
            "dprintf",
            "scanf",
            "fscanf",
            "sscanf",
            "syslog",
            "openlog",
            "closelog",
        ],
        "impure_call_targets": [
            "printf",
            "fprintf",
            "dprintf",
            "puts",
            "putchar",
            "scanf",
            "fscanf",
            "getchar",
            "gets",
            "time",
            "clock",
            "gettimeofday",
            "nanosleep",
            "rand",
            "srand",
            "random",
            "getenv",
            "setenv",
            "environ",
            "signal",
            "raise",
        ],
    },
)

# ── HCL (Terraform) ──────────────────────────────────────────────────────

_register(
    "hcl",
    {
        "extensions": [".tf", ".tfvars", ".hcl"],
        "import_path": "tree_sitter_hcl",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 8, "nesting_depth": 3, "function_length": 40},
        "queries": {
            "functions": "(block (identifier) @name) @func",
            "calls": "(function_call (identifier) @name) @call",
            "imports": "(function_call (identifier) @name) @call",
        },
        "ignore_names": [],
        "entry_points": [],
        "risky_call_targets": [
            "file",
            "fopen",
            "fread",
            "fwrite",
            "fclose",
            "remove",
            "rename",
            "mkdir",
            "rmdir",
            "system",
            "exec",
            "fork",
            "socket",
            "connect",
            "listen",
            "accept",
            "send",
            "recv",
            "http.get",
            "http.post",
            "json.parse",
            "json.stringify",
            "fmt",
            "print",
            "println",
            "std.fs.cwd",
            "std.fs.openDir",
            "std.fs.openFile",
            "std.fs.createFile",
            "std.fs.deleteFile",
            "std.fs.rename",
            "std.fs.makeDir",
            "std.fs.deleteDir",
            "std.net.tcpConnectToHost",
            "std.net.tcpConnectToAddress",
            "std.process.Child",
            "std.process.Child.spawn",
            "std.ChildProcess.exec",
            "std.os.exit",
        ],
        "impure_call_targets": [
            "std.debug.print",
            "std.log.info",
            "std.log.err",
            "std.time.microTimestamp",
            "std.time.nanoTimestamp",
            "std.time.sleep",
            "std.crypto.random.int",
            "std.crypto.random.bytes",
            "std.os.getenv",
            "std.os.args",
        ],
    },
)

# ── Zig ──────────────────────────────────────────────────────────────────

_register(
    "zig",
    {
        "extensions": [".zig"],
        "import_path": "tree_sitter_zig",
        "lang_attr": "language",
        "thresholds": {
            "parameter_count": 5,
            "nesting_depth": 4,
            "function_length": 50,
            "cyclomatic_complexity": 10,
            "cognitive_complexity": 15,
            "boolean_complexity": 3,
            "god_class_methods": 10,
            "god_class_deps": 6,
            "god_class_lines": 100,
        },
        "queries": {
            "functions": (
                "(function_declaration name: (identifier) @name (parameters) @params) @func"
            ),
            "calls": """
            (call_expression (identifier) @name) @call
            (call_expression (field_expression (identifier) (identifier) @name)) @call
        """,
            "imports": "(builtin_function (builtin_identifier) @name)",
        },
        "ignore_names": ["main"],
        "entry_points": ["main"],
        "risky_call_targets": [
            "std.fs.cwd",
            "std.fs.openDir",
            "std.fs.openFile",
            "std.fs.createFile",
            "std.fs.deleteFile",
            "std.fs.rename",
            "std.fs.makeDir",
            "std.fs.deleteDir",
            "std.fs.readDir",
            "std.fs.Dir.readFile",
            "std.fs.Dir.writeFile",
            "std.fs.Dir.copyFile",
            "std.fs.Dir.deleteFile",
            "std.net.tcpConnectToHost",
            "std.net.tcpConnectToAddress",
            "std.net.tcpServer",
            "std.net.Stream.read",
            "std.net.Stream.write",
            "std.http.Client.fetch",
            "std.http.Client.request",
            "std.http.Server.listen",
            "std.process.Child.spawn",
            "std.process.Child.kill",
            "std.ChildProcess.exec",
            "std.ChildProcess.run",
            "std.os.exit",
            "std.os.abort",
            "std.json.parseFromSlice",
            "std.json.stringify",
            "std.json.parseFromSliceLeaky",
            "std.debug.print",
            "std.log.info",
            "std.log.err",
            "std.io.getStdIn",
            "std.io.getStdOut",
            "std.io.getStdErr",
        ],
        "impure_call_targets": [
            "std.debug.print",
            "std.log.info",
            "std.log.err",
            "std.time.microTimestamp",
            "std.time.nanoTimestamp",
            "std.time.sleep",
            "std.time.Instant",
            "std.crypto.random.int",
            "std.crypto.random.bytes",
            "std.crypto.random.intRangeAtMost",
            "std.os.getenv",
            "std.os.args",
            "std.os.environ",
            "std.io.getStdOut",
            "std.io.getStdErr",
            "std.io.getStdIn",
        ],
        "decision_types": [
            "if_expression",
            "else_if",
            "for_expression",
            "while_expression",
            "catch_expression",
            "try_expression",
            "switch_expression",
            "boolean_operator",
        ],
        "boolean_operator_types": ["and", "or"],
    },
)

# ── Extension-to-language map (built lazily) ─────────────────────────────

_EXT_TO_LANG: dict[str, str] | None = None


def extension_to_language(ext: str) -> str | None:
    """Return the language name for a file extension, or None."""
    global _EXT_TO_LANG
    if _EXT_TO_LANG is None:
        _EXT_TO_LANG = {}
        for lang_name, defn in LANGUAGES.items():
            for e in defn["extensions"]:
                # Already registered? The first registration wins (priority order)
                if e not in _EXT_TO_LANG:
                    _EXT_TO_LANG[e] = lang_name
    return _EXT_TO_LANG.get(ext.lower())


# ── Parser cache (lazy, per-language) ────────────────────────────────────

_PARSERS: dict[str, Parser] = {}
_QUERIES_CACHE: dict[str, dict[str, Query]] = {}


def get_parser(lang: str) -> Parser:
    """Get or create a parser for the given language."""
    if lang not in _PARSERS:
        defn = LANGUAGES.get(lang)
        if not defn:
            raise ValueError(f"Unknown language: {lang}")
        _PARSERS[lang] = _make_parser(defn["import_path"], defn["lang_attr"])
    return _PARSERS[lang]


def get_queries(lang: str) -> dict[str, Query]:
    """Get or create compiled queries for the given language."""
    if lang not in _QUERIES_CACHE:
        defn = LANGUAGES.get(lang)
        if not defn:
            raise ValueError(f"Unknown language: {lang}")
        parser = get_parser(lang)
        lang_obj = parser.language
        assert lang_obj is not None, f"Parser for {lang} returned None language"
        queries: dict[str, Query] = {}
        for qname, qstr in defn["queries"].items():
            queries[qname] = Query(lang_obj, qstr)
        _QUERIES_CACHE[lang] = queries
    return _QUERIES_CACHE[lang]


def get_thresholds(lang: str) -> dict[str, int]:
    """Get thresholds for the given language."""
    defn = LANGUAGES.get(lang)
    if not defn:
        raise ValueError(f"Unknown language: {lang}")
    return dict(defn["thresholds"])


def get_ignore_names(lang: str) -> list[str]:
    """Get function names to ignore for the given language."""
    defn = LANGUAGES.get(lang)
    if not defn:
        return []
    return list(defn.get("ignore_names", []))


def get_entry_points(lang: str) -> list[str]:
    """Get entry point function names for the given language."""
    defn = LANGUAGES.get(lang)
    if not defn:
        return []
    return list(defn.get("entry_points", []))


def get_risky_call_targets(lang: str) -> list[str]:
    """Get risky call targets (functions that should be try-guarded) for a language."""
    defn = LANGUAGES.get(lang)
    if not defn:
        return []
    return list(defn.get("risky_call_targets", []))


def get_impure_call_targets(lang: str) -> list[str]:
    """Get known-impure function names for a language."""
    defn = LANGUAGES.get(lang)
    return list(defn.get("impure_call_targets", [])) if defn else []


def supported_extensions() -> list[str]:
    """Return list of all registered file extensions."""
    exts: list[str] = []
    for defn in LANGUAGES.values():
        exts.extend(defn["extensions"])
    return sorted(set(exts))
