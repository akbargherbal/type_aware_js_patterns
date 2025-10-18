/**
 * Complete Type-Aware Variable Transformation
 * 
 * Replaces ALL identifiers (declarations + usages) with their inferred types
 * Handles naming collisions with numeric suffixes
 */

import * as ts from "typescript";
import * as fs from "fs";
import * as path from "path";

/**
 * Sanitizes type names and handles collisions
 */
function sanitizeTypeName(typeString: string): string {
  // Handle union types - pick first non-null type
  if (typeString.includes(" | ")) {
    const types = typeString.split(" | ");
    const filtered = types.find(t => t !== "null" && t !== "undefined");
    typeString = filtered || "unknown";
  }

  // Handle array types: string[] -> StringArray
  if (typeString.endsWith("[]")) {
    const baseType = typeString.slice(0, -2);
    return sanitizeTypeName(baseType) + "Array";
  }

  // Handle generic types: Promise<T> -> Promise
  if (typeString.includes("<")) {
    return typeString.substring(0, typeString.indexOf("<"));
  }

  // Handle function types
  if (typeString.startsWith("(") && typeString.includes("=>")) {
    return "Function";
  }

  // Clean special characters
  return typeString.replace(/[^a-zA-Z0-9_]/g, "");
}

/**
 * Creates transformation that replaces ALL identifiers with types
 */
function createCompleteTypeTransformer(
  program: ts.Program
): ts.TransformerFactory<ts.SourceFile> {
  const checker = program.getTypeChecker();
  
  // Map original names to their types (with collision handling)
  const nameToType = new Map<string, string>();
  const typeUsageCount = new Map<string, number>();

  return (context: ts.TransformationContext) => {
    return (sourceFile: ts.SourceFile) => {
      
      // PASS 1: Collect all variable declarations and their types
      function collectTypes(node: ts.Node) {
        if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
          const originalName = node.name.getText();
          const symbol = checker.getSymbolAtLocation(node.name);
          
          if (symbol) {
            const type = checker.getTypeOfSymbolAtLocation(symbol, node);
            let typeString = checker.typeToString(type);
            
            // Skip if type is 'any' or 'unknown' - keep original name
            if (typeString === "any" || typeString === "unknown") {
              console.log(`  ⚠️  Skipping ${originalName} (type: ${typeString})`);
              return;
            }
            
            let sanitized = sanitizeTypeName(typeString);
            
            // Handle naming collisions by adding numeric suffix
            const count = typeUsageCount.get(sanitized) || 0;
            typeUsageCount.set(sanitized, count + 1);
            
            if (count > 0) {
              sanitized = `${sanitized}${count}`;
            }
            
            nameToType.set(originalName, sanitized);
            console.log(`  ${originalName} → ${typeString} → ${sanitized}`);
          }
        }
        
        ts.forEachChild(node, collectTypes);
      }
      
      collectTypes(sourceFile);
      
      // PASS 2: Replace all identifiers (declarations + usages)
      const visitor = (node: ts.Node): ts.Node => {
        // Replace variable declaration names
        if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
          const originalName = node.name.getText();
          const newName = nameToType.get(originalName);
          
          if (newName) {
            return ts.factory.updateVariableDeclaration(
              node,
              ts.factory.createIdentifier(newName),
              node.exclamationToken,
              node.type,
              node.initializer ? ts.visitNode(node.initializer, visitor) as ts.Expression : undefined
            );
          }
        }
        
        // Replace identifier usages (but not property names)
        if (ts.isIdentifier(node)) {
          const originalName = node.getText();
          const newName = nameToType.get(originalName);
          
          // Don't replace if it's a property access (e.g., object.property)
          const parent = node.parent;
          if (parent && ts.isPropertyAccessExpression(parent) && parent.name === node) {
            return node; // Keep property names as-is
          }
          
          if (newName) {
            return ts.factory.createIdentifier(newName);
          }
        }
        
        return ts.visitEachChild(node, visitor, context);
      };

      return ts.visitNode(sourceFile, visitor) as ts.SourceFile;
    };
  };
}

/**
 * Main transformation with proper DOM type loading
 */
function transformWithProperTypes(inputFile: string, outputFile: string): string {
  if (!fs.existsSync(inputFile)) {
    throw new Error(`File not found: ${inputFile}`);
  }

  console.log(`\n🔍 Analyzing: ${inputFile}\n`);
  
  const source = fs.readFileSync(inputFile, "utf-8");

  // CRITICAL: Use ts.createCompilerHost for proper type loading
  const compilerOptions: ts.CompilerOptions = {
    allowJs: true,
    checkJs: true,
    target: ts.ScriptTarget.ESNext,
    lib: ["lib.dom.d.ts", "lib.es2015.d.ts"],
    noEmit: false,
    strict: false,
  };

  // Use the proper compiler host that loads lib.d.ts files
  const host = ts.createCompilerHost(compilerOptions);
  const program = ts.createProgram([inputFile], compilerOptions, host);
  
  const sourceFile = program.getSourceFile(inputFile);
  if (!sourceFile) {
    throw new Error(`Could not load source file: ${inputFile}`);
  }

  console.log("📊 Type Mapping:\n");
  
  // Transform
  const transformer = createCompleteTypeTransformer(program);
  const result = ts.transform(sourceFile, [transformer]);
  const transformedFile = result.transformed[0];
  
  // Emit
  const printer = ts.createPrinter({ newLine: ts.NewLineKind.LineFeed });
  const output = printer.printFile(transformedFile);
  
  result.dispose();
  
  return output;
}

/**
 * CLI Entry Point
 */
function main() {
  const args = process.argv.slice(2);
  
  if (args.length < 1) {
    console.error("Usage: ts-node transform_complete.ts <input.js> [output.js]");
    console.error("\nExample: ts-node transform_complete.ts sample_app.js converted_output.js");
    process.exit(1);
  }

  const inputFile = args[0];
  const outputFile = args[1] || inputFile.replace(/\.js$/, "_transformed.js");

  try {
    const transformed = transformWithProperTypes(inputFile, outputFile);
    
    if (!transformed || transformed.trim().length === 0) {
      throw new Error("Transformation produced empty output!");
    }

    fs.writeFileSync(outputFile, transformed, "utf-8");
    console.log(`\n✅ Transformation complete!`);
    console.log(`📄 Output: ${outputFile}`);
    console.log(`📏 Size: ${transformed.length} bytes\n`);
    
  } catch (error) {
    console.error("❌ Error:", error instanceof Error ? error.message : error);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

export { transformWithProperTypes };