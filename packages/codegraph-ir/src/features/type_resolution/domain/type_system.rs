//! SOTA Type System with Union/Intersection Support
//!
//! Comprehensive type representation for Python static analysis.
//!
//! Features:
//! - Union types: `int | str | None`
//! - Intersection types: Protocol composition
//! - Generic types: `List[int]`, `Dict[str, int]`
//! - Literal types: `Literal[42]`, `Literal["hello"]`
//! - Type variables: `TypeVar("T")`
//!
//! Quick Win: ~200 LOC, enables Union type analysis

use std::collections::HashSet;
use std::fmt;

/// Type kind categorization
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum TypeKind {
    /// Simple type: int, str, bool
    Simple(String),
    /// None type
    None,
    /// Any type (top type)
    Any,
    /// Never type (bottom type)
    Never,
    /// Generic type: List[T], Dict[K, V]
    Generic { base: String, params: Vec<Type> },
    /// Union type: int | str | None
    Union(Vec<Type>),
    /// Intersection type: Protocol1 & Protocol2
    Intersection(Vec<Type>),
    /// Callable type: (int, str) -> bool
    Callable {
        params: Vec<Type>,
        return_type: Box<Type>,
    },
    /// Literal type: Literal[42], Literal["hello"]
    Literal(String),
    /// Type variable: TypeVar("T")
    TypeVar(String),
}

/// Type representation
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Type {
    pub kind: TypeKind,
}

impl Type {
    /// Create a simple type
    pub fn simple(name: impl Into<String>) -> Self {
        Self {
            kind: TypeKind::Simple(name.into()),
        }
    }

    /// Create None type
    pub fn none() -> Self {
        Self {
            kind: TypeKind::None,
        }
    }

    /// Create Any type
    pub fn any() -> Self {
        Self {
            kind: TypeKind::Any,
        }
    }

    /// Create Never type
    pub fn never() -> Self {
        Self {
            kind: TypeKind::Never,
        }
    }

    /// Create generic type
    pub fn generic(base: impl Into<String>, params: Vec<Type>) -> Self {
        Self {
            kind: TypeKind::Generic {
                base: base.into(),
                params,
            },
        }
    }

    /// Create union type
    pub fn union(types: Vec<Type>) -> Self {
        // Flatten nested unions
        let mut flattened = Vec::new();
        for ty in types {
            match ty.kind {
                TypeKind::Union(inner) => flattened.extend(inner),
                _ => flattened.push(ty),
            }
        }

        // Remove duplicates
        let unique = Self::deduplicate(flattened);

        // Simplify single-element unions
        if unique.len() == 1 {
            return unique.into_iter().next().unwrap();
        }

        Self {
            kind: TypeKind::Union(unique),
        }
    }

    /// Create intersection type
    pub fn intersection(types: Vec<Type>) -> Self {
        // Flatten nested intersections
        let mut flattened = Vec::new();
        for ty in types {
            match ty.kind {
                TypeKind::Intersection(inner) => flattened.extend(inner),
                _ => flattened.push(ty),
            }
        }

        // Remove duplicates
        let unique = Self::deduplicate(flattened);

        // Simplify single-element intersections
        if unique.len() == 1 {
            return unique.into_iter().next().unwrap();
        }

        Self {
            kind: TypeKind::Intersection(unique),
        }
    }

    /// Create callable type
    pub fn callable(params: Vec<Type>, return_type: Type) -> Self {
        Self {
            kind: TypeKind::Callable {
                params,
                return_type: Box::new(return_type),
            },
        }
    }

    /// Create literal type
    pub fn literal(value: impl Into<String>) -> Self {
        Self {
            kind: TypeKind::Literal(value.into()),
        }
    }

    /// Create type variable
    pub fn type_var(name: impl Into<String>) -> Self {
        Self {
            kind: TypeKind::TypeVar(name.into()),
        }
    }

    /// Check if type is nullable (contains None in union)
    pub fn is_nullable(&self) -> bool {
        match &self.kind {
            TypeKind::None => true,
            TypeKind::Union(types) => types.iter().any(|t| matches!(t.kind, TypeKind::None)),
            _ => false,
        }
    }

    /// Check if type is a union
    pub fn is_union(&self) -> bool {
        matches!(self.kind, TypeKind::Union(_))
    }

    /// Get union members if this is a union type
    pub fn union_members(&self) -> Option<&[Type]> {
        match &self.kind {
            TypeKind::Union(types) => Some(types),
            _ => None,
        }
    }

    /// Check if type is compatible with another type
    pub fn is_compatible_with(&self, other: &Type) -> bool {
        // Any is compatible with everything
        if matches!(self.kind, TypeKind::Any) || matches!(other.kind, TypeKind::Any) {
            return true;
        }

        // Never is compatible with nothing
        if matches!(self.kind, TypeKind::Never) {
            return false;
        }

        // Same type
        if self == other {
            return true;
        }

        // Union compatibility: self is compatible if it's a member of the union
        if let TypeKind::Union(types) = &other.kind {
            return types.iter().any(|t| self.is_compatible_with(t));
        }

        false
    }

    /// Remove duplicate types from a list
    fn deduplicate(types: Vec<Type>) -> Vec<Type> {
        let mut seen = HashSet::new();
        let mut unique = Vec::new();

        for ty in types {
            if seen.insert(ty.clone()) {
                unique.push(ty);
            }
        }

        unique
    }
}

impl fmt::Display for Type {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.kind {
            TypeKind::Simple(name) => write!(f, "{}", name),
            TypeKind::None => write!(f, "None"),
            TypeKind::Any => write!(f, "Any"),
            TypeKind::Never => write!(f, "Never"),
            TypeKind::Generic { base, params } => {
                write!(f, "{}", base)?;
                if !params.is_empty() {
                    write!(f, "[")?;
                    for (i, param) in params.iter().enumerate() {
                        if i > 0 {
                            write!(f, ", ")?;
                        }
                        write!(f, "{}", param)?;
                    }
                    write!(f, "]")?;
                }
                Ok(())
            }
            TypeKind::Union(types) => {
                for (i, ty) in types.iter().enumerate() {
                    if i > 0 {
                        write!(f, " | ")?;
                    }
                    write!(f, "{}", ty)?;
                }
                Ok(())
            }
            TypeKind::Intersection(types) => {
                for (i, ty) in types.iter().enumerate() {
                    if i > 0 {
                        write!(f, " & ")?;
                    }
                    write!(f, "{}", ty)?;
                }
                Ok(())
            }
            TypeKind::Callable {
                params,
                return_type,
            } => {
                write!(f, "(")?;
                for (i, param) in params.iter().enumerate() {
                    if i > 0 {
                        write!(f, ", ")?;
                    }
                    write!(f, "{}", param)?;
                }
                write!(f, ") -> {}", return_type)
            }
            TypeKind::Literal(value) => write!(f, "Literal[{}]", value),
            TypeKind::TypeVar(name) => write!(f, "{}", name),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_type() {
        let ty = Type::simple("int");
        assert_eq!(ty.to_string(), "int");
    }

    #[test]
    fn test_union_type() {
        let ty = Type::union(vec![Type::simple("int"), Type::simple("str"), Type::none()]);
        assert_eq!(ty.to_string(), "int | str | None");
        assert!(ty.is_nullable());
        assert!(ty.is_union());
    }

    #[test]
    fn test_union_flattening() {
        let inner_union = Type::union(vec![Type::simple("int"), Type::simple("str")]);
        let outer_union = Type::union(vec![inner_union, Type::none()]);

        // Should flatten to int | str | None
        assert_eq!(outer_union.to_string(), "int | str | None");
    }

    #[test]
    fn test_union_deduplication() {
        let ty = Type::union(vec![
            Type::simple("int"),
            Type::simple("str"),
            Type::simple("int"), // duplicate
        ]);

        let members = ty.union_members().unwrap();
        assert_eq!(members.len(), 2);
    }

    #[test]
    fn test_generic_type() {
        let ty = Type::generic("List", vec![Type::simple("int")]);
        assert_eq!(ty.to_string(), "List[int]");
    }

    #[test]
    fn test_nested_generic() {
        let inner = Type::generic("List", vec![Type::simple("int")]);
        let outer = Type::generic("Dict", vec![Type::simple("str"), inner]);
        assert_eq!(outer.to_string(), "Dict[str, List[int]]");
    }

    #[test]
    fn test_callable_type() {
        let ty = Type::callable(
            vec![Type::simple("int"), Type::simple("str")],
            Type::simple("bool"),
        );
        assert_eq!(ty.to_string(), "(int, str) -> bool");
    }

    #[test]
    fn test_literal_type() {
        let ty = Type::literal("42");
        assert_eq!(ty.to_string(), "Literal[42]");
    }

    #[test]
    fn test_intersection_type() {
        let ty = Type::intersection(vec![Type::simple("Protocol1"), Type::simple("Protocol2")]);
        assert_eq!(ty.to_string(), "Protocol1 & Protocol2");
    }

    #[test]
    fn test_compatibility() {
        let int_ty = Type::simple("int");
        let union_ty = Type::union(vec![Type::simple("int"), Type::simple("str")]);

        assert!(int_ty.is_compatible_with(&union_ty));
        assert!(int_ty.is_compatible_with(&Type::any()));
        assert!(!int_ty.is_compatible_with(&Type::simple("str")));
    }

    #[test]
    fn test_nullable_detection() {
        let non_nullable = Type::simple("int");
        assert!(!non_nullable.is_nullable());

        let nullable = Type::union(vec![Type::simple("int"), Type::none()]);
        assert!(nullable.is_nullable());
    }
}
