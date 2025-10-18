# Type-Aware JavaScript Code Pattern Mining

## 🎯 Project Purpose

This project implements a **type-aware code transformation pipeline** for large-scale code pattern mining across JavaScript/TypeScript repositories. The goal is to normalize JavaScript code by replacing variable names with their inferred types, enabling pattern analysis that transcends naming conventions.

> **Philosophy**: This is a **"good enough" approach** optimized for scale, not 100% accuracy. We aim for 70-85% type inference coverage to capture recurring patterns across repositories. Perfect type inference is neither necessary nor practical for pattern mining at scale.

### The Problem We're Solving

When mining code patterns across 150+ GitHub repositories, variable naming conventions obscure actual behavioral patterns:

```javascript
// Repository A
const input = document.getElementById("search");
input.value = "";

// Repository B
const searchBox = document.getElementById("query");
searchBox.value = "";

// Repository C
const txtQuery = document.getElementById("input");
txtQuery.value = "";
```

These are **the same pattern** (`HTMLElement.value = ""`) but with different variable names. Traditional pattern mining (like tree-sitter) would count these as three separate patterns because tree-sitters are **syntactically correct but type-blind**.

### Our Solution

Transform code to replace variable names with their TypeScript-inferred types:

```javascript
// After transformation - ALL THREE become:
const HTMLElement = document.getElementById("...");
HTMLElement.value = "";
```

Now we can count unified patterns like:

- `HTMLElement.innerHTML`
- `Array.map().filter().forEach()`
- `HTMLLIElement.textContent`
- `HTMLParagraphElement.appendChild()`

## 📊 Project Specifications

### Scale & Performance

- **Target**: ~150 GitHub repositories (thousands of JS/TS/JSX/TSX files)
- **Processing Speed**: 1500 files per hour (max 2.4 seconds per file)
- **Infrastructure**: Single GCP VM (~$1/9 hours)
- **Timeline**: 3-4 days including setup

### Accuracy Requirements (Pragmatic Approach)

**Target: 70-85% type coverage** - This is intentionally "good enough":

- ✅ **70-85% type accuracy is acceptable** (some `unknown` or `any` is fine)
- ✅ **Generic types are fine** (`Array` instead of `Array<string>`)
- ✅ **Third-party library types can be generic** or skipped
- ✅ **Naming collisions are acceptable** (multiple `HTMLElement` variables)
- ✅ **Some patterns will be missed** (e.g., arrays from `any` chains)
- ⚠️ **Output code doesn't need to be functional** (analysis-only)

**Why 70-85% is sufficient:**

- DOM patterns (our primary target) have high inference rates
- Missing some array/string patterns is acceptable loss
- Scale matters more than perfection - we're processing 150+ repos
- Pattern frequency will reveal what matters most

**Trade-off Philosophy:**

- ✅ **Fast and scalable** > Perfect type inference
- ✅ **Captures most common patterns** > Captures every edge case
- ✅ **Ship and iterate** > Debug every `any` type
- ✅ **Data-driven decisions** > Theoretical completeness

### What Success Looks Like

**Input** (`sample_app.js`):

```javascript
const input = document.getElementById("input");
const words = text.split(/\s+/);
const li = document.createElement("li");
```

**Output** (`converted_output.js`):

```javascript
const HTMLElement = document.getElementById("input");
const words = text.split(/\s+/); // May stay as-is if 'text' is 'any'
const HTMLLIElement = document.createElement("li");
```

Now we can count patterns across all repos:

- `HTMLElement` is referenced 45,203 times
- `HTMLElement.addEventListener()` appears in 8,942 code locations
- `HTMLLIElement.textContent` used 1,234 times

**Note**: Some patterns like `words.forEach()` may not be normalized if TypeScript can't infer the type through `any` chains. This is acceptable - we focus on high-value, high-frequency patterns.

## 🗃️ Technical Architecture

### The TypeScript Compiler API Pipeline

This project leverages TypeScript's type inference engine (the same system VS Code uses) to extract type information from plain JavaScript files:

```
┌──────────────────┐
│ Input: JS File  │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────┐
│ TypeScript Compiler API     │
│ - Load DOM type definitions │
│ - Infer variable types      │
│ - Build type mapping        │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ AST Transformation          │
│ - Replace declarations      │
│ - Replace usages            │
│ - Handle collisions         │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Output: Type-Normalized JS  │
└─────────────────────────────┘
```

### Key Components

1. **TypeScript Program** - Creates type-checking context with DOM APIs loaded
2. **TypeChecker** - Infers types for all variables (leverages `lib.dom.d.ts`)
3. **AST Transformer** - Rewrites syntax tree to replace identifiers
4. **Collision Handler** - Manages duplicate type names (`HTMLElement`, `HTMLElement1`, etc.)
5. **Statistics Tracker** - Monitors coverage and identifies missing patterns

## 🚀 Usage

### Installation

```bash
npm install
```

### Basic Transformation

```bash
npx ts-node type_transform_poc.ts sample_app.js converted_output.js
```

### Validation & Coverage Analysis

See exactly what patterns you're capturing vs. missing:

```bash
npx ts-node poc_validation.ts
```

**Output includes:**

- Type inference coverage percentage
- Type breakdown (HTMLElement, HTMLLIElement, etc.)
- Captured patterns by category (DOM, Array, String)
- **Critical gap analysis** - shows missed array/string patterns
- GO/NO-GO recommendation for scaling

### Diagnostic Mode

Understand why TypeScript infers specific types:

```bash
npx ts-node diagnostic_script.ts
```

## 📂 File Structure

```
.
├── README.md                    # This file
├── package.json                 # Dependencies (TypeScript, ts-node)
├── tsconfig.json                # TypeScript configuration
│
├── sample_app.js                # Example input file (DOM manipulation)
│
├── type_transform_poc.ts        # Main transformer (declarations + usages)
├── poc_validation.ts            # ⭐ Final validation with coverage stats
├── diagnostic_script.ts         # Type inference diagnostic tool
│
├── converted_output.js          # Example output (generated)
└── test_output.js               # Test transformation output
```

## 🔬 How Type Inference Works

### The Four Pillars of JS Type Inference

TypeScript can infer types from plain JavaScript when configured correctly:

```typescript
const compilerOptions = {
  allowJs: true, // Accept .js files
  checkJs: true, // Enable type checking
  target: ts.ScriptTarget.ESNext, // Modern JS features
  lib: ["lib.dom.d.ts", "lib.es2015.d.ts"], // Browser + ES2015 APIs
};
```

### Type Inference Examples

| JavaScript Code                | Inferred Type                   | Coverage Status   |
| ------------------------------ | ------------------------------- | ----------------- |
| `document.getElementById("x")` | `HTMLElement`                   | ✅ High accuracy  |
| `document.createElement("li")` | `HTMLLIElement`                 | ✅ High accuracy  |
| `[1,2,3].map(...)`             | `number[]`                      | ✅ High accuracy  |
| `text.split(/\s+/)`            | `any[]` if text is `any`        | ⚠️ Missed pattern |
| `input.value.trim()`           | `any` if input is `HTMLElement` | ⚠️ Missed pattern |

### Known Limitations (Expected Behavior)

⚠️ **TypeScript CANNOT infer specific element types from `getElementById()`:**

```javascript
const input = document.getElementById("input");
// Type: HTMLElement (NOT HTMLInputElement)
// Why: The string "input" is just a value, not a type hint
```

This is **correct behavior** - TypeScript has no way to know what HTML elements exist at runtime.

⚠️ **Type inference breaks through `any` chains:**

```javascript
const text = input.value.trim(); // HTMLElement.value doesn't exist → 'any'
const words = text.split(/\s+/); // any.split() → 'any[]'
```

**Impact**: Array/string method patterns may not be normalized in ~30% of cases.

**Mitigation**: Focus on high-frequency patterns that DO get inferred correctly (DOM manipulation, explicit arrays, typed functions).

## 📊 Expected Coverage Across 150 Repos

Based on POC validation, expect:

**High Coverage (80-90%):**

- DOM element creation: `document.createElement()`
- DOM queries: `document.getElementById()`, `querySelector()`
- DOM manipulation: `.appendChild()`, `.innerHTML`, `.textContent`

**Medium Coverage (60-75%):**

- Array literals: `[1,2,3].map()` ✅
- Explicit types: TypeScript files, JSDoc hints ✅
- Function returns with known types ✅

**Low Coverage (30-50%):**

- Arrays from `any` chains: `unknownVar.split()` ❌
- String operations on `any`: `unknownVar.trim()` ❌
- Dynamic property access: `obj[key]` ❌

**Decision Point**: After processing 10-20 repos, if array pattern coverage is below 40%, consider adding JSDoc preprocessing for common patterns.

## 🎓 Research Background

This implementation is based on research into TypeScript's Compiler API and Language Server Protocol. Key findings:

1. **VS Code's Intelligence** - VS Code uses TypeScript Language Server, which uses the same TypeChecker API we use
2. **Type Definition Loading** - Must use `ts.createCompilerHost()` to properly load `lib.dom.d.ts`
3. **Two-Pass Transformation** - Collect types first, then replace identifiers (handles forward references)
4. **Performance at Scale** - TypeScript can process files quickly with proper configuration
5. **Pragmatic Trade-offs** - 70% accuracy at scale beats 100% accuracy that never ships

## ⚙️ Configuration

### Compiler Options

Fine-tune type inference behavior in `type_transform_poc.ts`:

```typescript
const compilerOptions: ts.CompilerOptions = {
  allowJs: true, // Process .js files
  checkJs: true, // Enable type inference
  strict: false, // Lenient mode (more permissive)
  lib: [
    "lib.dom.d.ts", // Browser APIs (document, window, etc.)
    "lib.es2015.d.ts", // Modern JavaScript features
  ],
};
```

### Type Sanitization

Control how TypeScript types map to valid JavaScript identifiers:

```typescript
function sanitizeTypeName(typeString: string): string {
  // "HTMLElement | null" → "HTMLElement"
  // "string[]" → "StringArray"
  // "Promise<string>" → "Promise"
  // "(e: Event) => void" → "Function"
}
```

## 📈 Performance Metrics

From test runs on `sample_app.js` (1.2KB):

- **Analysis Time**: ~0.5 seconds
- **Type Inference**: 5/7 variables typed (71% success rate)
- **Patterns Captured**: 8 unique patterns
- **Patterns Missed**: 2 (array methods from `any` chain)
- **Output Size**: 1.3KB (minimal overhead)

Extrapolated to 1500 files/hour:

- **Per-file time**: 2.4 seconds (within target)
- **Total processing**: ~4 hours for 150 repos
- **Expected type coverage**: 70-75% across repos

## 🔧 Troubleshooting

### Common Issues

**Problem**: Everything returns `any`

```bash
# Check: Are you using ts.createCompilerHost()?
# Fix: See type_transform_poc.ts for correct setup
```

**Problem**: Low type coverage (< 60%)

```bash
# Run validation to see what's missing:
npx ts-node poc_validation.ts

# If missing mostly array patterns, consider JSDoc preprocessing
```

**Problem**: Cannot find module errors

```bash
npm install
```

**Problem**: "Output would overwrite input"

```bash
# Always specify different output filename
npx ts-node type_transform_poc.ts input.js output.js
```

## 🎯 Future Enhancements

Potential improvements for production scale:

1. **Batch Processing** - Process entire repositories in parallel
2. **JSDoc Preprocessing** - Add type hints for common `any` chain patterns
3. **Type Definition Caching** - Cache DefinitelyTyped definitions for common libraries
4. **Incremental Compilation** - Reuse type information across files in same repo
5. **Library Type Resolution** - Handle `import` statements and `node_modules`
6. **Pattern Extraction Pipeline** - Build pattern counting directly into the transformer

## 📚 References

- [TypeScript Compiler API Documentation](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API)
- [TypeScript AST Viewer](https://ts-ast-viewer.com/) - Visualize syntax trees
- [DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped) - Type definitions for JavaScript libraries

## 📄 License

This is a research proof-of-concept for academic code analysis.

## 🤝 Contributing

This is a solo research project, but the techniques demonstrated are reusable for:

- Code pattern mining at scale
- Static analysis of JavaScript codebases
- Type-aware code transformations
- AST manipulation with TypeScript

---

**Status**: POC Validated ✅ (71% type coverage, meets target)  
**Next Phase**: Scale to 150 repositories for full pattern mining analysis  
**Philosophy**: Ship fast, iterate based on data, optimize for scale over perfection
