/**
 * Final POC Validation with Detailed Coverage Statistics
 * 
 * Shows exactly what patterns we're capturing vs missing
 * before scaling to 150 repositories
 */

import * as ts from "typescript";
import * as fs from "fs";
import * as path from "path";

// Statistics tracking
interface TransformStats {
  totalVariables: number;
  typedVariables: number;
  skippedAny: number;
  typeBreakdown: Map<string, number>;
  skippedReasons: Map<string, number>;
}

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
  program: ts.Program,
  stats: TransformStats
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
          
          stats.totalVariables++;
          
          if (symbol) {
            const type = checker.getTypeOfSymbolAtLocation(symbol, node);
            let typeString = checker.typeToString(type);
            
            // Try to infer from initializer if we got 'any'
            if ((typeString === "any" || typeString === "unknown") && node.initializer) {
              const initType = checker.getTypeAtLocation(node.initializer);
              const initTypeString = checker.typeToString(initType);
              
              // Use initializer type if it's more specific
              if (initTypeString !== "any" && initTypeString !== "unknown") {
                typeString = initTypeString;
                console.log(`  🔄 ${originalName} → inferred from initializer: ${typeString}`);
                stats.typedVariables++;
                stats.typeBreakdown.set(typeString, (stats.typeBreakdown.get(typeString) || 0) + 1);
              } else {
                console.log(`  ⚠️  Skipping ${originalName} (type: ${typeString})`);
                stats.skippedAny++;
                stats.skippedReasons.set(`any_from_${initTypeString}`, 
                  (stats.skippedReasons.get(`any_from_${initTypeString}`) || 0) + 1);
                return;
              }
            } else if (typeString === "any" || typeString === "unknown") {
              console.log(`  ⚠️  Skipping ${originalName} (type: ${typeString})`);
              stats.skippedAny++;
              stats.skippedReasons.set(typeString, (stats.skippedReasons.get(typeString) || 0) + 1);
              return;
            } else {
              stats.typedVariables++;
              stats.typeBreakdown.set(typeString, (stats.typeBreakdown.get(typeString) || 0) + 1);
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
function transformWithProperTypes(inputFile: string, outputFile: string): { output: string; stats: TransformStats } {
  if (!fs.existsSync(inputFile)) {
    throw new Error(`File not found: ${inputFile}`);
  }

  console.log(`\n🔍 Analyzing: ${inputFile}\n`);
  
  const source = fs.readFileSync(inputFile, "utf-8");

  // Initialize statistics
  const stats: TransformStats = {
    totalVariables: 0,
    typedVariables: 0,
    skippedAny: 0,
    typeBreakdown: new Map(),
    skippedReasons: new Map(),
  };

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
  const transformer = createCompleteTypeTransformer(program, stats);
  const result = ts.transform(sourceFile, [transformer]);
  const transformedFile = result.transformed[0];
  
  // Emit
  const printer = ts.createPrinter({ newLine: ts.NewLineKind.LineFeed });
  const output = printer.printFile(transformedFile);
  
  result.dispose();
  
  return { output, stats };
}

/**
 * Extract patterns from transformed code
 */
function extractPatterns(code: string): Array<{ pattern: string; count: number; category: string }> {
  const patternMap = new Map<string, number>();
  
  // Match patterns like: TypeName.method()
  const methodPattern = /(\w+)\.([\w]+)\(/g;
  let match;
  
  while ((match = methodPattern.exec(code)) !== null) {
    const pattern = `${match[1]}.${match[2]}()`;
    patternMap.set(pattern, (patternMap.get(pattern) || 0) + 1);
  }
  
  // Convert to array and sort by count
  const patterns = Array.from(patternMap.entries())
    .map(([pattern, count]) => {
      // Categorize patterns
      let category = "Other";
      if (pattern.startsWith("HTML")) category = "DOM";
      if (pattern.startsWith("Array") || pattern.includes("Array.")) category = "Array";
      if (pattern.startsWith("String") || pattern.includes("String.")) category = "String";
      if (pattern.startsWith("document.")) category = "Document";
      
      return { pattern, count, category };
    })
    .sort((a, b) => b.count - a.count);
  
  return patterns;
}

/**
 * Analyze what patterns we're missing
 */
function analyzeMissingPatterns(originalCode: string, transformedCode: string): {
  missedArrayPatterns: string[];
  missedStringPatterns: string[];
  totalMissed: number;
} {
  const missedArrayPatterns: string[] = [];
  const missedStringPatterns: string[] = [];
  
  // Check for array methods that weren't type-normalized
  const arrayMethods = ["forEach", "map", "filter", "reduce", "find", "some", "every"];
  arrayMethods.forEach(method => {
    const regex = new RegExp(`\\w+\\.${method}\\(`, "g");
    const matches = originalCode.match(regex);
    if (matches) {
      matches.forEach(m => {
        if (!transformedCode.includes(`Array.${method}(`)) {
          missedArrayPatterns.push(m);
        }
      });
    }
  });
  
  // Check for string methods that weren't type-normalized
  const stringMethods = ["split", "trim", "toLowerCase", "toUpperCase", "substring", "slice"];
  stringMethods.forEach(method => {
    const regex = new RegExp(`\\w+\\.${method}\\(`, "g");
    const matches = originalCode.match(regex);
    if (matches) {
      matches.forEach(m => {
        if (!transformedCode.includes(`String.${method}(`)) {
          missedStringPatterns.push(m);
        }
      });
    }
  });
  
  return {
    missedArrayPatterns: [...new Set(missedArrayPatterns)],
    missedStringPatterns: [...new Set(missedStringPatterns)],
    totalMissed: missedArrayPatterns.length + missedStringPatterns.length
  };
}

/**
 * Final validation with comprehensive statistics
 */
function runFinalValidation() {
  console.log("\n" + "=".repeat(80));
  console.log("🎯 FINAL POC VALIDATION - Type-Aware Pattern Mining");
  console.log("=".repeat(80));

  const inputFile = "sample_app.js";
  const outputFile = "final_output.js";

  try {
    const originalCode = fs.readFileSync(inputFile, "utf-8");
    const { output, stats } = transformWithProperTypes(inputFile, outputFile);
    
    fs.writeFileSync(outputFile, output, "utf-8");
    
    // Extract patterns
    const patterns = extractPatterns(output);
    const missing = analyzeMissingPatterns(originalCode, output);
    
    // Print comprehensive statistics
    console.log("\n" + "=".repeat(80));
    console.log("📊 COVERAGE STATISTICS");
    console.log("=".repeat(80));
    
    console.log(`\n📈 Type Inference Coverage:`);
    console.log(`   Total Variables:     ${stats.totalVariables}`);
    console.log(`   Successfully Typed:  ${stats.typedVariables} (${(stats.typedVariables/stats.totalVariables*100).toFixed(1)}%)`);
    console.log(`   Skipped (any):       ${stats.skippedAny} (${(stats.skippedAny/stats.totalVariables*100).toFixed(1)}%)`);
    
    console.log(`\n🔍 Type Breakdown:`);
    const sortedTypes = Array.from(stats.typeBreakdown.entries())
      .sort((a, b) => b[1] - a[1]);
    sortedTypes.forEach(([type, count]) => {
      console.log(`   ${type.padEnd(30)} ${count} occurrence(s)`);
    });
    
    console.log(`\n⚠️  Reasons for Skipping:`);
    stats.skippedReasons.forEach((count, reason) => {
      console.log(`   ${reason.padEnd(30)} ${count} occurrence(s)`);
    });
    
    console.log(`\n🎯 Pattern Extraction Results:`);
    console.log(`   Total Unique Patterns: ${patterns.length}`);
    
    // Group by category
    const byCategory = new Map<string, typeof patterns>();
    patterns.forEach(p => {
      if (!byCategory.has(p.category)) {
        byCategory.set(p.category, []);
      }
      byCategory.get(p.category)!.push(p);
    });
    
    byCategory.forEach((pats, category) => {
      console.log(`\n   📁 ${category} Patterns (${pats.length} unique):`);
      pats.slice(0, 5).forEach(p => {
        console.log(`      ${p.pattern.padEnd(40)} ${p.count}x`);
      });
      if (pats.length > 5) {
        console.log(`      ... and ${pats.length - 5} more`);
      }
    });
    
    console.log(`\n❌ MISSING PATTERNS (Critical Gap Analysis):`);
    console.log(`   Missed Array Patterns:  ${missing.missedArrayPatterns.length}`);
    if (missing.missedArrayPatterns.length > 0) {
      missing.missedArrayPatterns.forEach(p => {
        console.log(`      🔴 ${p}`);
      });
    }
    
    console.log(`   Missed String Patterns: ${missing.missedStringPatterns.length}`);
    if (missing.missedStringPatterns.length > 0) {
      missing.missedStringPatterns.forEach(p => {
        console.log(`      🔴 ${p}`);
      });
    }
    
    console.log(`\n   Total Missed:           ${missing.totalMissed} patterns`);
    
    // Final recommendation
    console.log("\n" + "=".repeat(80));
    console.log("💡 RECOMMENDATION");
    console.log("=".repeat(80));
    
    const typeCoverage = (stats.typedVariables/stats.totalVariables*100);
    const missRate = missing.totalMissed;
    
    if (typeCoverage >= 70 && missRate <= 2) {
      console.log(`\n✅ POC PASSES - Ready to scale!`);
      console.log(`   - Type coverage: ${typeCoverage.toFixed(1)}% (target: 70%+)`);
      console.log(`   - Missing patterns: ${missRate} (acceptable)`);
      console.log(`   - Capturing ${patterns.length} unique patterns`);
      console.log(`\n🚀 NEXT STEP: Build orchestration for 150 repositories`);
    } else if (typeCoverage >= 70 && missRate > 2) {
      console.log(`\n⚠️  POC NEEDS ADJUSTMENT - Type coverage OK but missing critical patterns`);
      console.log(`   - Type coverage: ${typeCoverage.toFixed(1)}% ✅`);
      console.log(`   - Missing patterns: ${missRate} ❌ (especially Array methods)`);
      console.log(`\n🔧 RECOMMENDATION: Add JSDoc preprocessing for array/string inference`);
      console.log(`   This will capture .map(), .filter(), .forEach() patterns`);
    } else {
      console.log(`\n❌ POC NEEDS WORK - Below target coverage`);
      console.log(`   - Type coverage: ${typeCoverage.toFixed(1)}% (target: 70%+)`);
      console.log(`   - Missing patterns: ${missRate}`);
      console.log(`\n🔧 RECOMMENDATION: Investigate type inference configuration`);
    }
    
    console.log("\n" + "=".repeat(80));
    console.log(`📄 Transformed output written to: ${outputFile}`);
    console.log("=".repeat(80) + "\n");
    
  } catch (error) {
    console.error("\n❌ ERROR:", error instanceof Error ? error.message : error);
    process.exit(1);
  }
}

/**
 * CLI Entry Point
 */
if (require.main === module) {
  runFinalValidation();
}

export { transformWithProperTypes, extractPatterns, analyzeMissingPatterns };