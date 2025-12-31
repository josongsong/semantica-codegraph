pub mod builtin_types;
pub mod dependent_types;
pub mod gradual_typing;
pub mod refinement_types;
pub mod type_entity;
pub mod type_system;

pub use type_entity::{TypeEntity, TypeFlavor, TypeResolutionLevel};

// Re-export SOTA type system types
pub use builtin_types::{
    get_builtin_function, get_builtin_type, BuiltinFunction, BUILTIN_FUNCTIONS, BUILTIN_TYPES,
};
pub use type_system::{Type, TypeKind};

// Re-export gradual typing
pub use gradual_typing::{
    check_gradual_guarantee, is_consistent, BlameInfo, BlameLabel, BlamePolarity, BlameTracker,
    CastInserter, CastKind, ConsistencyResult, GradualGuaranteeResult, TypeCast,
};

// Re-export refinement types
pub use refinement_types::{
    is_subtype, ArithExpr, CompOp, Predicate, RefinementAliases, RefinementType, SubtypeResult, Var,
};

// Re-export dependent types
pub use dependent_types::{
    DependentReturnType, DependentTypePatterns, IndexConstraint, IndexConstraintSolver, IndexExpr,
    IndexVar, IndexedType, PiType, SigmaType,
};
