#!/usr/bin/env node
/**
 * ts-morph TypeScript Analyzer
 *
 * Python에서 호출하는 TypeScript 분석 스크립트.
 * stdin으로 JSON 명령 받고 stdout으로 JSON 결과 반환.
 */

const { Project } = require('ts-morph');
const fs = require('fs');
const path = require('path');

// Read stdin
let input = '';
process.stdin.on('data', (chunk) => {
  input += chunk;
});

process.stdin.on('end', () => {
  try {
    const payload = JSON.parse(input);
    const result = handleCommand(payload);
    console.log(JSON.stringify(result));
  } catch (error) {
    console.error(JSON.stringify({ error: error.message }));
    process.exit(1);
  }
});

function handleCommand(payload) {
  const { command, params, project_root } = payload;

  // Initialize project
  const project = initProject(project_root);

  switch (command) {
    case 'get_type':
      return getTypeAtLocation(project, params);
    case 'get_definition':
      return getDefinition(project, params);
    case 'get_references':
      return getReferences(project, params);
    case 'analyze_file':
      return analyzeFile(project, params);
    default:
      throw new Error(`Unknown command: ${command}`);
  }
}

function initProject(projectRoot) {
  // Try to find tsconfig.json
  const tsconfigPath = path.join(projectRoot, 'tsconfig.json');

  if (fs.existsSync(tsconfigPath)) {
    return new Project({
      tsConfigFilePath: tsconfigPath,
      skipAddingFilesFromTsConfig: false,
    });
  }

  // Fallback: create project without tsconfig
  return new Project({
    compilerOptions: {
      target: 99, // Latest
      module: 99, // ES2020
      lib: ['lib.es2020.d.ts'],
      strict: false,
      esModuleInterop: true,
      skipLibCheck: true,
    },
  });
}

function getTypeAtLocation(project, { file_path, line, column }) {
  let sourceFile = project.getSourceFile(file_path);
  if (!sourceFile) {
    // Try to add the file
    try {
      sourceFile = project.addSourceFileAtPath(file_path);
    } catch (error) {
      return { error: `Failed to load file: ${error.message}` };
    }
  }
  if (!sourceFile) {
    return { error: `File not found: ${file_path}` };
  }

  try {
    // Get node at position
    const pos = sourceFile.compilerNode.getPositionOfLineAndCharacter(line - 1, column);
    const node = sourceFile.getDescendantAtPos(pos);

    if (!node) {
      return { type: 'unknown', is_union: false };
    }

    // Get type
    const type = node.getType();
    const typeText = type.getText();

    // Check if union type
    const isUnion = type.isUnion();
    const unionVariants = isUnion
      ? type.getUnionTypes().map(t => t.getText())
      : [];

    return {
      type: typeText,
      is_union: isUnion,
      union_variants: unionVariants,
    };
  } catch (error) {
    return { error: error.message };
  }
}

function getDefinition(project, { file_path, line, column }) {
  let sourceFile = project.getSourceFile(file_path);
  if (!sourceFile) {
    sourceFile = project.addSourceFileAtPath(file_path);
  }
  if (!sourceFile) {
    return { definitions: [] };
  }

  const pos = sourceFile.compilerNode.getPositionOfLineAndCharacter(line - 1, column);
  const node = sourceFile.getDescendantAtPos(pos);

  if (!node) {
    return { definitions: [] };
  }

  const definitions = node.getDefinitionNodes().map(def => {
    const sourceFile = def.getSourceFile();
    const { line, character } = sourceFile.getLineAndColumnAtPos(def.getStart());

    return {
      file_path: sourceFile.getFilePath(),
      line: line,
      column: character,
    };
  });

  return { definitions };
}

function getReferences(project, { file_path, line, column }) {
  let sourceFile = project.getSourceFile(file_path);
  if (!sourceFile) {
    try {
      sourceFile = project.addSourceFileAtPath(file_path);
    } catch (error) {
      return { references: [] };
    }
  }
  if (!sourceFile) {
    return { references: [] };
  }

  try {
    const pos = sourceFile.compilerNode.getPositionOfLineAndCharacter(line - 1, column);
    const node = sourceFile.getDescendantAtPos(pos);

    if (!node) {
      return { references: [] };
    }

    const refs = node.findReferencesAsNodes().map(ref => {
      const refSourceFile = ref.getSourceFile();
      const { line, character } = refSourceFile.getLineAndColumnAtPos(ref.getStart());

      return {
        file_path: refSourceFile.getFilePath(),
        line: line,
        column: character,
      };
    });

    return { references: refs };
  } catch (error) {
    return { references: [], error: error.message };
  }
}

function analyzeFile(project, { file_path }) {
  let sourceFile = project.getSourceFile(file_path);
  if (!sourceFile) {
    // Try to add the file
    try {
      sourceFile = project.addSourceFileAtPath(file_path);
    } catch (error) {
      return { error: `Failed to load file: ${error.message}` };
    }
  }
  if (!sourceFile) {
    return { error: `File not found: ${file_path}` };
  }

  const result = {
    functions: [],
    classes: [],
    interfaces: [],
    variables: [],
    imports: [],
    exports: [],
  };

  // Functions
  sourceFile.getFunctions().forEach(func => {
    result.functions.push({
      name: func.getName(),
      parameters: func.getParameters().map(p => ({
        name: p.getName(),
        type: p.getType().getText(),
      })),
      return_type: func.getReturnType().getText(),
      signature: func.getType().getText(),
    });
  });

  // Classes
  sourceFile.getClasses().forEach(cls => {
    const methods = cls.getMethods().map(m => ({
      name: m.getName(),
      parameters: m.getParameters().map(p => ({
        name: p.getName(),
        type: p.getType().getText(),
      })),
      return_type: m.getReturnType().getText(),
    }));

    const properties = cls.getProperties().map(p => ({
      name: p.getName(),
      type: p.getType().getText(),
    }));

    result.classes.push({
      name: cls.getName(),
      methods,
      properties,
      extends: cls.getExtends()?.getText() || null,
      implements: cls.getImplements().map(i => i.getText()),
    });
  });

  // Interfaces
  sourceFile.getInterfaces().forEach(iface => {
    const properties = iface.getProperties().map(p => ({
      name: p.getName(),
      type: p.getType().getText(),
    }));

    result.interfaces.push({
      name: iface.getName(),
      properties,
      extends: iface.getExtends().map(e => e.getText()),
    });
  });

  // Variables
  sourceFile.getVariableDeclarations().forEach(varDecl => {
    result.variables.push({
      name: varDecl.getName(),
      type: varDecl.getType().getText(),
    });
  });

  // Imports
  sourceFile.getImportDeclarations().forEach(imp => {
    result.imports.push({
      module: imp.getModuleSpecifierValue(),
      named: imp.getNamedImports().map(n => n.getName()),
      default: imp.getDefaultImport()?.getText() || null,
    });
  });

  // Exports
  sourceFile.getExportDeclarations().forEach(exp => {
    result.exports.push({
      module: exp.getModuleSpecifierValue() || null,
      named: exp.getNamedExports().map(n => n.getName()),
    });
  });

  return result;
}
