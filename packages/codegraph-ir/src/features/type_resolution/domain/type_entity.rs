//! Type entity domain model

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TypeFlavor {
    Builtin,
    User,
    External,
}

impl TypeFlavor {
    pub fn as_str(&self) -> &'static str {
        match self {
            TypeFlavor::Builtin => "builtin",
            TypeFlavor::User => "user",
            TypeFlavor::External => "external",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TypeResolutionLevel {
    Raw,
    Builtin,
    Local,
    Module,
    Project,
    External,
}

impl TypeResolutionLevel {
    pub fn as_str(&self) -> &'static str {
        match self {
            TypeResolutionLevel::Raw => "raw",
            TypeResolutionLevel::Builtin => "builtin",
            TypeResolutionLevel::Local => "local",
            TypeResolutionLevel::Module => "module",
            TypeResolutionLevel::Project => "project",
            TypeResolutionLevel::External => "external",
        }
    }
}

#[derive(Debug, Clone)]
pub struct TypeEntity {
    pub id: String,
    pub raw: String,
    pub flavor: TypeFlavor,
    pub is_nullable: bool,
    pub resolution_level: TypeResolutionLevel,
    pub resolved_target: Option<String>,
    pub generic_param_ids: Vec<String>,
}
