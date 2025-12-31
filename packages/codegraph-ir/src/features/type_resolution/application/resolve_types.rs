use crate::features::ir_generation::domain::IRDocument;
use crate::features::type_resolution::domain::TypeEntity;
use crate::features::type_resolution::ports::TypeResolver;
use crate::shared::models::Result;

pub struct ResolveTypesUseCase<R: TypeResolver> {
    resolver: R,
}

impl<R: TypeResolver> ResolveTypesUseCase<R> {
    pub fn new(resolver: R) -> Self {
        Self { resolver }
    }

    pub fn execute(&self, ir: &IRDocument) -> Result<Vec<TypeEntity>> {
        self.resolver.resolve(ir)
    }
}
