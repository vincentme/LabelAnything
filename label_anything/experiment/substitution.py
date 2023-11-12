import torch

from einops import rearrange

from label_anything.data.utils import mean_pairwise_j_index
from label_anything.data.transforms import PromptsProcessor


def cartesian_product(a, b):
    # Create 1D tensors for indices along each dimension
    indices_a = torch.arange(a)
    indices_b = torch.arange(b)

    return torch.cartesian_prod(indices_a, indices_b)


def generate_points_from_errors(
    prediction: torch.tensor,
    ground_truth: torch.tensor,
    num_points: int,
    ignore_index: int = -100,
):
    """
    Generates a point for each class that can be positive or negative depending on the error being false positive or false negative.
    Args:
        prediction (torch.Tensor): The predicted segmentation mask of shape (batch_size, num_classes, height, width)
        ground_truth (torch.Tensor): The ground truth segmentation mask of shape (batch_size, num_classes, height, width)
        num_points (int): The number of points to generate for each class
    """
    B, C = prediction.shape[:2]
    device = prediction.device
    ground_truth = ground_truth.clone()
    ground_truth[ground_truth == ignore_index] = 0
    ground_truth = rearrange(
        torch.nn.functional.one_hot(ground_truth, C),
        "b h w c -> b c h w",
    )
    prediction = prediction.argmax(dim=1)
    prediction = rearrange(
        torch.nn.functional.one_hot(prediction, C),
        "b h w c -> b c h w",
    )
    errors = ground_truth - prediction
    coords = torch.nonzero(errors)
    classes, counts = torch.unique(
        coords[:, 0:2], dim=0, return_counts=True, sorted=True
    )
    sampled_idxs = torch.cat(
        [torch.randint(0, x, (num_points,), device=device) for x in counts]
    ) + torch.cat([torch.tensor([0], device=device), counts.cumsum(dim=0)])[
        :-1
    ].repeat_interleave(
        num_points
    )
    sampled_points = coords[sampled_idxs]
    labels = errors[
        sampled_points[:, 0],
        sampled_points[:, 1],
        sampled_points[:, 2],
        sampled_points[:, 3],
    ]
    all_classes = cartesian_product(B, C)
    missing = torch.tensor(
        list(
            set(tuple(elem) for elem in all_classes.tolist())
            - set(tuple(elem) for elem in classes.tolist())
        ),
        device=device,
    )
    missing = torch.cat([missing, torch.zeros(missing.shape, device=device)], dim=1)
    sampled_points = torch.cat([sampled_points, missing], dim=0)
    _, indices = torch.sort(sampled_points[:, :2], dim=0)
    sampled_points = torch.index_select(sampled_points, 0, indices[:, 1])

    labels = torch.cat([labels, torch.zeros(missing.shape[0], device=device)])
    labels = torch.index_select(labels, 0, indices[:, 1])

    sampled_points = rearrange(
        sampled_points[:, 2:4],
        "(b c n) xy -> b c n xy",
        n=num_points,
        c=errors.shape[1],
    )
    labels = rearrange(labels, "(b c n) -> b c n", n=num_points, c=errors.shape[1])
    return sampled_points, labels


class Substitutor:
    """
    A class that cycle all the images in the examples as a query image.
    """

    torch_keys_to_exchange = [
        "prompt_points",
        "prompt_masks",
        "prompt_bboxes",
        "flag_masks",
        "flag_bboxes",
        "flag_points",
        "dims",
    ]
    torch_keys_to_separate = [
        "prompt_points",
        "prompt_masks",
        "prompt_bboxes",
        "flag_masks",
        "flag_bboxes",
        "flag_points",
    ]
    list_keys_to_exchange = ["classes"]
    list_keys_to_separate = ["classes"]

    def __init__(
        self, batch: dict, threshold: float = None, num_points: int = 1
    ) -> None:
        self.batch, self.ground_truths = batch
        self.example_classes = self.batch["classes"]
        self.threshold = threshold
        self.num_points = num_points
        self.substitute = self.calculate_if_substitute()
        self.it = 0
        self.prompt_processor = PromptsProcessor()

    def calculate_if_substitute(self):
        if self.threshold is None:
            return True
        return (
            torch.mean(
                torch.tensor(
                    [mean_pairwise_j_index(elem) for elem in self.example_classes]
                )
            )
            > self.threshold
        )

    def __iter__(self):
        return self

    def generate_new_points(self, prediction, ground_truth):
        """
        Generate new points from predictions errors and add them to the prompts
        """
        if self.substitute:
            sampled_points, labels = generate_points_from_errors(
                prediction, ground_truth, self.num_points
            )
            sampled_points = torch.stack(
                [
                    self.prompt_processor.torch_apply_coords(elem, dim[0])
                    for dim, elem in zip(self.batch["dims"], sampled_points)
                ]
            )
            sampled_points = rearrange(sampled_points, "b c n xy -> b 1 c n xy")
            padding_points = torch.zeros(
                sampled_points.shape[0],
                self.batch["prompt_points"].shape[1] - 1,
                *sampled_points.shape[2:],
                device=sampled_points.device,
            )
            labels = rearrange(labels, "b c n -> b 1 c n")
            padding_labels = torch.zeros(
                labels.shape[0],
                self.batch["flag_points"].shape[1] - 1,
                *labels.shape[2:],
                device=labels.device,
            )
            sampled_points = torch.cat([padding_points, sampled_points], dim=1)
            labels = torch.cat([padding_labels, labels], dim=1)

            self.batch["prompt_points"] = torch.cat(
                [self.batch["prompt_points"], sampled_points], dim=3
            )
            self.batch["flag_points"] = torch.cat(
                [self.batch["flag_points"], labels], dim=3
            )

    def divide_query_examples(self):
        batch_examples = {}
        for key in self.torch_keys_to_separate:
            batch_examples[key] = self.batch[key][:, 1:]
        for key in self.list_keys_to_separate:
            batch_examples[key] = [elem[1:] for elem in self.batch[key]]
        gt = self.ground_truths[:, 0]
        for key in self.batch.keys() - set(
            self.torch_keys_to_separate + self.list_keys_to_separate
        ):
            batch_examples[key] = self.batch[key]
        if "embeddings" in self.batch:
            batch_examples["embeddings"] = self.batch["embeddings"]
        elif "images" in self.batch:
            batch_examples["images"] = self.batch["images"]
        else:
            raise ValueError("Batch must contain either images or embeddings")
        return batch_examples, gt

    def __next__(self):
        if "images" in self.batch:
            self.torch_keys_to_exchange.append("images")
            num_examples = self.batch["images"].shape[1]
            device = self.batch["images"].device
        elif "embeddings" in self.batch:
            self.torch_keys_to_exchange.append("embeddings")
            num_examples = self.batch["embeddings"].shape[1]
            device = self.batch["embeddings"].device
        else:
            raise ValueError("Batch must contain either images or embeddings")

        if self.it == 0:
            self.it = 1
            return self.divide_query_examples()
        if not self.substitute:
            raise StopIteration
        if self.it == num_examples:
            raise StopIteration

        index_tensor = torch.cat(
            [
                torch.tensor([self.it], device=device),
                torch.arange(0, self.it, device=device),
                torch.arange(self.it + 1, num_examples, device=device),
            ]
        ).long()

        for key in self.torch_keys_to_exchange:
            self.batch[key] = torch.index_select(
                self.batch[key], dim=1, index=index_tensor
            )

        for key in self.list_keys_to_exchange:
            self.batch[key] = [
                [elem[i] for i in index_tensor] for elem in self.batch[key]
            ]
        for key in self.batch.keys() - set(
            self.torch_keys_to_exchange + self.list_keys_to_exchange
        ):
            self.batch[key] = self.batch[key]

        self.ground_truths = torch.index_select(
            self.ground_truths, dim=1, index=index_tensor
        )

        self.it += 1
        return self.divide_query_examples()