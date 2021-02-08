from typing import TYPE_CHECKING, Iterable, Optional, Set, Union

from ..page.models import Page
from ..product.models import Category, Collection, Product, ProductVariant
from .models import (
    AssignedCategoryAttribute,
    AssignedCategoryAttributeValue,
    AssignedCollectionAttribute,
    AssignedCollectionAttributeValue,
    AssignedPageAttribute,
    AssignedPageAttributeValue,
    AssignedProductAttribute,
    AssignedProductAttributeValue,
    AssignedVariantAttribute,
    AssignedVariantAttributeValue,
    Attribute,
    AttributeValue,
)

AttributeAssignmentType = Union[
    AssignedProductAttribute,
    AssignedVariantAttribute,
    AssignedPageAttribute,
    AssignedCategoryAttribute,
]
T_INSTANCE = Union[Product, ProductVariant, Page, Collection]


if TYPE_CHECKING:
    from ..site.models import SiteSettings
    from .models import AttributePage, AttributeProduct, AttributeVariant


def associate_attribute_values_to_instance(
    instance: T_INSTANCE,
    attribute: Attribute,
    values: Iterable[AttributeValue],
    site_settings: Optional["SiteSettings"] = None,
) -> AttributeAssignmentType:
    """Assign given attribute values to a product or variant.

    Note: be award this function invokes the ``set`` method on the instance's
    attribute association. Meaning any values already assigned or concurrently
    assigned will be overridden by this call.
    """
    values_ids = {value.pk for value in values}

    # Ensure the values are actually form the given attribute
    validate_attribute_owns_values(attribute, values_ids)

    # Associate the attribute and the passed values
    assignment = _associate_attribute_to_instance(instance, attribute.pk, site_settings)
    assignment.values.set(values)
    sort_assigned_attribute_values(instance, assignment, values)

    return assignment


def validate_attribute_owns_values(attribute: Attribute, value_ids: Set[int]) -> None:
    """Check given value IDs are belonging to the given attribute.

    :raise: AssertionError
    """
    attribute_actual_value_ids = set(attribute.values.values_list("pk", flat=True))
    found_associated_ids = attribute_actual_value_ids & value_ids
    if found_associated_ids != value_ids:
        raise AssertionError("Some values are not from the provided attribute.")


def _associate_attribute_to_instance(
    instance: T_INSTANCE,
    attribute_pk: int,
    site_settings: Optional["SiteSettings"] = None,
) -> AttributeAssignmentType:
    """Associate a given attribute to an instance."""
    assignment: AttributeAssignmentType
    if isinstance(instance, Product):
        attribute_rel: Union[
            "AttributeProduct", "AttributeVariant", "AttributePage"
        ] = instance.product_type.attributeproduct.get(attribute_id=attribute_pk)

        assignment, _ = AssignedProductAttribute.objects.get_or_create(
            product=instance, assignment=attribute_rel
        )
    elif isinstance(instance, ProductVariant):
        attribute_rel = instance.product.product_type.attributevariant.get(
            attribute_id=attribute_pk
        )

        assignment, _ = AssignedVariantAttribute.objects.get_or_create(
            variant=instance, assignment=attribute_rel
        )
    elif isinstance(instance, Page):
        attribute_rel = instance.page_type.attributepage.get(attribute_id=attribute_pk)
        assignment, _ = AssignedPageAttribute.objects.get_or_create(
            page=instance, assignment=attribute_rel
        )
    elif isinstance(instance, Category) or isinstance(instance, Collection):
        assignment = _get_associate_category_or_collection_attribute(
            instance, attribute_pk, site_settings
        )
    else:
        raise AssertionError(f"{instance.__class__.__name__} is unsupported")

    return assignment


def _get_associate_category_or_collection_attribute(
    instance: Union[Category, Collection],
    attribute_pk: int,
    site_settings: Optional["SiteSettings"] = None,
):
    instance_to_assignment_mapping = {
        "Category": ("category_attributes", AssignedCategoryAttribute),
        "Collection": ("collection_attributes", AssignedCollectionAttribute),
    }
    model_name = instance.__class__.__name__
    assignment_lookup, assignment_model = instance_to_assignment_mapping[model_name]

    attribute_rel = getattr(site_settings, assignment_lookup).get(
        attribute_id=attribute_pk
    )
    assignment, _ = assignment_model.objects.get_or_create(
        assignment=attribute_rel, **{model_name.lower(): instance}  # type: ignore
    )
    return assignment


def sort_assigned_attribute_values(
    instance: T_INSTANCE,
    assignment: AttributeAssignmentType,
    values: Iterable[AttributeValue],
) -> None:
    """Sort assigned attribute values based on values list order."""

    instance_to_value_assignment_mapping = {
        "Product": ("productvalueassignment", AssignedProductAttributeValue),
        "ProductVariant": ("variantvalueassignment", AssignedVariantAttributeValue),
        "Page": ("pagevalueassignment", AssignedPageAttributeValue),
        "Category": ("categoryvalueassignment", AssignedCategoryAttributeValue),
        "Collection": ("collectionvalueassignment", AssignedCollectionAttributeValue),
    }
    assignment_lookup, assignment_model = instance_to_value_assignment_mapping[
        instance.__class__.__name__
    ]
    values_pks = [value.pk for value in values]

    values_assignment = list(
        getattr(assignment, assignment_lookup).select_related("value")
    )
    values_assignment.sort(key=lambda e: values_pks.index(e.value.pk))
    for index, value_assignment in enumerate(values_assignment):
        value_assignment.sort_order = index

    assignment_model.objects.bulk_update(values_assignment, ["sort_order"])
