use crate::features::ir_generation::domain::IRDocument;
use crate::features::type_resolution::domain::TypeEntity;
use crate::shared::models::Result;

pub trait TypeResolver: Send + Sync {
    fn resolve(&self, ir: &IRDocument) -> Result<Vec<TypeEntity>>;
}
