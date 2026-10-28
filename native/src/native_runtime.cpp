#include <algorithm>
#include <cmath>
#include <cstddef>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#if ROVEREDGE_HAS_ACCELERATE
#include <Accelerate/Accelerate.h>
#endif

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;
using Matrix = std::vector<std::vector<float>>;

namespace {

void blocked_matmul_into(const Matrix& left, const Matrix& right, Matrix& output,
                         std::size_t block_size);
void parallel_blocked_matmul_into(const Matrix& left, const Matrix& right, Matrix& output,
                                  std::size_t block_size, std::size_t worker_count);

void validate_matrix(const Matrix& matrix, const std::string& name) {
  if (matrix.empty() || matrix.front().empty()) {
    throw std::invalid_argument(name + " must be a nonempty rectangular matrix");
  }
  const auto width = matrix.front().size();
  for (const auto& row : matrix) {
    if (row.size() != width) {
      throw std::invalid_argument(name + " must be rectangular");
    }
    if (!std::all_of(row.begin(), row.end(), [](float value) { return std::isfinite(value); })) {
      throw std::invalid_argument(name + " values must be finite");
    }
  }
}

Matrix matmul(const Matrix& left, const Matrix& right) {
  validate_matrix(left, "left operand");
  validate_matrix(right, "right operand");
  if (left.front().size() != right.size()) {
    throw std::invalid_argument("matrix dimensions do not align");
  }
  Matrix output(left.size(), std::vector<float>(right.front().size(), 0.0F));
  for (std::size_t row = 0; row < left.size(); ++row) {
    for (std::size_t inner = 0; inner < right.size(); ++inner) {
      const float left_value = left[row][inner];
      for (std::size_t column = 0; column < right.front().size(); ++column) {
        output[row][column] += left_value * right[inner][column];
      }
    }
  }
  return output;
}

Matrix blocked_matmul(const Matrix& left, const Matrix& right, std::size_t block_size) {
  validate_matrix(left, "left operand");
  validate_matrix(right, "right operand");
  if (block_size == 0) throw std::invalid_argument("block size must be positive");
  if (left.front().size() != right.size()) {
    throw std::invalid_argument("matrix dimensions do not align");
  }
  Matrix output(left.size(), std::vector<float>(right.front().size(), 0.0F));
  blocked_matmul_into(left, right, output, block_size);
  return output;
}

Matrix accelerate_matmul(const Matrix& left, const Matrix& right) {
  validate_matrix(left, "left operand");
  validate_matrix(right, "right operand");
  if (left.front().size() != right.size()) {
    throw std::invalid_argument("matrix dimensions do not align");
  }
#if ROVEREDGE_HAS_ACCELERATE
  const auto rows = left.size();
  const auto inner = right.size();
  const auto columns = right.front().size();
  std::vector<float> flat_left;
  std::vector<float> flat_right;
  flat_left.reserve(rows * inner);
  flat_right.reserve(inner * columns);
  for (const auto& row : left) flat_left.insert(flat_left.end(), row.begin(), row.end());
  for (const auto& row : right) flat_right.insert(flat_right.end(), row.begin(), row.end());
  std::vector<float> flat_output(rows * columns, 0.0F);
  cblas_sgemm(CblasRowMajor, CblasNoTrans, CblasNoTrans, static_cast<int>(rows),
              static_cast<int>(columns), static_cast<int>(inner), 1.0F, flat_left.data(),
              static_cast<int>(inner), flat_right.data(), static_cast<int>(columns), 0.0F,
              flat_output.data(), static_cast<int>(columns));
  Matrix output(rows, std::vector<float>(columns));
  for (std::size_t row = 0; row < rows; ++row) {
    std::copy_n(flat_output.begin() + static_cast<std::ptrdiff_t>(row * columns), columns,
                output[row].begin());
  }
  return output;
#else
  throw std::runtime_error("Apple Accelerate backend is unavailable on this host");
#endif
}

Matrix parallel_blocked_matmul(const Matrix& left, const Matrix& right,
                               std::size_t block_size, std::size_t worker_count) {
  validate_matrix(left, "left operand");
  validate_matrix(right, "right operand");
  if (block_size == 0) throw std::invalid_argument("block size must be positive");
  if (worker_count == 0) throw std::invalid_argument("worker count must be positive");
  if (left.front().size() != right.size()) {
    throw std::invalid_argument("matrix dimensions do not align");
  }
  Matrix output(left.size(), std::vector<float>(right.front().size(), 0.0F));
  parallel_blocked_matmul_into(left, right, output, block_size, worker_count);
  return output;
}

void parallel_blocked_matmul_into(const Matrix& left, const Matrix& right, Matrix& output,
                                  std::size_t block_size, std::size_t worker_count) {
  if (block_size == 0) throw std::invalid_argument("block size must be positive");
  if (worker_count == 0) throw std::invalid_argument("worker count must be positive");
  if (left.empty() || right.empty() || left.front().size() != right.size() ||
      output.size() != left.size() || output.front().size() != right.front().size()) {
    throw std::invalid_argument("matrix workspace dimensions do not align");
  }
  for (auto& row : output) std::fill(row.begin(), row.end(), 0.0F);
  const auto workers = std::min(worker_count, left.size());
  const auto rows_per_worker = (left.size() + workers - 1) / workers;
  std::vector<std::jthread> threads;
  threads.reserve(workers);
  for (std::size_t worker = 0; worker < workers; ++worker) {
    const auto row_begin = worker * rows_per_worker;
    const auto row_end = std::min(row_begin + rows_per_worker, left.size());
    if (row_begin == row_end) break;
    threads.emplace_back([&, row_begin, row_end] {
      for (std::size_t row_block = row_begin; row_block < row_end; row_block += block_size) {
        for (std::size_t inner_block = 0; inner_block < right.size(); inner_block += block_size) {
          for (std::size_t column_block = 0; column_block < right.front().size();
               column_block += block_size) {
            const auto block_row_end = std::min(row_block + block_size, row_end);
            const auto inner_end = std::min(inner_block + block_size, right.size());
            const auto column_end =
                std::min(column_block + block_size, right.front().size());
            for (std::size_t row = row_block; row < block_row_end; ++row) {
              for (std::size_t inner = inner_block; inner < inner_end; ++inner) {
                const float left_value = left[row][inner];
                for (std::size_t column = column_block; column < column_end; ++column) {
                  output[row][column] += left_value * right[inner][column];
                }
              }
            }
          }
        }
      }
    });
  }
}

void matmul_into(const Matrix& left, const Matrix& right, Matrix& output) {
  if (left.empty() || right.empty() || left.front().size() != right.size() ||
      output.size() != left.size() || output.front().size() != right.front().size()) {
    throw std::invalid_argument("matrix workspace dimensions do not align");
  }
  for (auto& row : output) std::fill(row.begin(), row.end(), 0.0F);
  for (std::size_t row = 0; row < left.size(); ++row) {
    for (std::size_t inner = 0; inner < right.size(); ++inner) {
      const float left_value = left[row][inner];
      for (std::size_t column = 0; column < right.front().size(); ++column) {
        output[row][column] += left_value * right[inner][column];
      }
    }
  }
}

void blocked_matmul_into(const Matrix& left, const Matrix& right, Matrix& output,
                         std::size_t block_size) {
  if (block_size == 0) throw std::invalid_argument("block size must be positive");
  if (left.empty() || right.empty() || left.front().size() != right.size() ||
      output.size() != left.size() || output.front().size() != right.front().size()) {
    throw std::invalid_argument("matrix workspace dimensions do not align");
  }
  for (auto& row : output) std::fill(row.begin(), row.end(), 0.0F);
  for (std::size_t row_block = 0; row_block < left.size(); row_block += block_size) {
    for (std::size_t inner_block = 0; inner_block < right.size(); inner_block += block_size) {
      for (std::size_t column_block = 0; column_block < right.front().size();
           column_block += block_size) {
        const auto row_end = std::min(row_block + block_size, left.size());
        const auto inner_end = std::min(inner_block + block_size, right.size());
        const auto column_end = std::min(column_block + block_size, right.front().size());
        for (std::size_t row = row_block; row < row_end; ++row) {
          for (std::size_t inner = inner_block; inner < inner_end; ++inner) {
            const float left_value = left[row][inner];
            for (std::size_t column = column_block; column < column_end; ++column) {
              output[row][column] += left_value * right[inner][column];
            }
          }
        }
      }
    }
  }
}

Matrix transpose(const Matrix& source) {
  validate_matrix(source, "weight matrix");
  Matrix result(source.front().size(), std::vector<float>(source.size()));
  for (std::size_t row = 0; row < source.size(); ++row) {
    for (std::size_t column = 0; column < source.front().size(); ++column) {
      result[column][row] = source[row][column];
    }
  }
  return result;
}

void add_bias_and_relu(Matrix& values, const std::vector<float>& bias, bool relu) {
  if (values.empty() || values.front().size() != bias.size()) {
    throw std::invalid_argument("bias dimensions do not align");
  }
  for (auto& row : values) {
    for (std::size_t column = 0; column < row.size(); ++column) {
      row[column] += bias[column];
      if (relu) {
        row[column] = std::max(0.0F, row[column]);
      }
    }
  }
}

class NativeRiskModel {
 public:
  NativeRiskModel(std::vector<float> mean, std::vector<float> scale,
                  std::vector<Matrix> weights, std::vector<std::vector<float>> biases,
                  std::string backend, std::size_t block_size, std::size_t worker_count)
      : mean_(std::move(mean)),
        scale_(std::move(scale)),
        biases_(std::move(biases)),
        normalized_(8, std::vector<float>(24)),
        hidden_one_(8, std::vector<float>(64)),
        hidden_two_(8, std::vector<float>(32)),
        logit_matrix_(8, std::vector<float>(1)),
        logits_(8),
        scores_(8),
        backend_(std::move(backend)),
        block_size_(block_size),
        worker_count_(worker_count) {
    if (mean_.size() != 24 || scale_.size() != 24 || weights.size() != 3 ||
        biases_.size() != 3) {
      throw std::invalid_argument("model dimensions do not match 24-64-32-1");
    }
    if (backend_ != "native-naive" && backend_ != "native-blocked" &&
        backend_ != "native-parallel-blocked" && backend_ != "native-accelerate") {
      throw std::invalid_argument("unsupported native inference backend");
    }
#if !ROVEREDGE_HAS_ACCELERATE
    if (backend_ == "native-accelerate") {
      throw std::runtime_error("Apple Accelerate backend is unavailable on this host");
    }
#endif
    if (block_size_ == 0) throw std::invalid_argument("block size must be positive");
    if (worker_count_ == 0) throw std::invalid_argument("worker count must be positive");
    for (float value : mean_) {
      if (!std::isfinite(value)) throw std::invalid_argument("normalization must be finite");
    }
    for (float value : scale_) {
      if (!std::isfinite(value) || value <= 0.0F) {
        throw std::invalid_argument("normalization scale must be finite and positive");
      }
    }
    for (const auto& bias : biases_) {
      if (!std::all_of(bias.begin(), bias.end(),
                       [](float value) { return std::isfinite(value); })) {
        throw std::invalid_argument("model biases must be finite");
      }
    }
    weights_.reserve(3);
    for (const auto& weight : weights) weights_.push_back(transpose(weight));
    if (weights_[0].size() != 24 || weights_[0].front().size() != 64 ||
        weights_[1].size() != 64 || weights_[1].front().size() != 32 ||
        weights_[2].size() != 32 || weights_[2].front().size() != 1 ||
        biases_[0].size() != 64 || biases_[1].size() != 32 || biases_[2].size() != 1) {
      throw std::invalid_argument("model dimensions do not match 24-64-32-1");
    }
    if (backend_ == "native-accelerate") {
      flat_weights_.reserve(weights_.size());
      for (const auto& weight : weights_) {
        std::vector<float> flat;
        flat.reserve(weight.size() * weight.front().size());
        for (const auto& row : weight) flat.insert(flat.end(), row.begin(), row.end());
        flat_weights_.push_back(std::move(flat));
      }
      accelerate_left_.resize(8 * 64);
      accelerate_output_.resize(8 * 64);
    }
  }

  py::dict evaluate(const Matrix& batch) {
    std::unique_lock<std::mutex> lock(workspace_mutex_, std::try_to_lock);
    if (!lock.owns_lock()) {
      throw std::runtime_error("native workspace is already in use by an overlapping call");
    }
    validate_matrix(batch, "feature batch");
    if (batch.size() != 8 || batch.front().size() != 24) {
      throw std::invalid_argument("native inference requires an 8 by 24 feature batch");
    }
    for (std::size_t row = 0; row < batch.size(); ++row) {
      for (std::size_t index = 0; index < batch[row].size(); ++index) {
        normalized_[row][index] = (batch[row][index] - mean_[index]) / scale_[index];
      }
    }
    multiply_into(normalized_, weights_[0], hidden_one_, 0);
    add_bias_and_relu(hidden_one_, biases_[0], true);
    multiply_into(hidden_one_, weights_[1], hidden_two_, 1);
    add_bias_and_relu(hidden_two_, biases_[1], true);
    multiply_into(hidden_two_, weights_[2], logit_matrix_, 2);
    for (std::size_t row = 0; row < batch.size(); ++row) {
      logits_[row] = logit_matrix_[row][0] + biases_[2][0];
      scores_[row] = 1.0F / (1.0F + std::exp(-logits_[row]));
    }
    py::gil_scoped_acquire acquire;
    py::dict result;
    result["hidden_one"] = hidden_one_;
    result["hidden_two"] = hidden_two_;
    result["logits"] = logits_;
    result["scores"] = scores_;
    return result;
  }

 private:
  void multiply_into(const Matrix& left, const Matrix& right, Matrix& output,
                     std::size_t layer_index) {
    if (backend_ == "native-parallel-blocked") {
      parallel_blocked_matmul_into(left, right, output, block_size_, worker_count_);
    } else if (backend_ == "native-blocked") {
      blocked_matmul_into(left, right, output, block_size_);
    } else if (backend_ == "native-accelerate") {
#if ROVEREDGE_HAS_ACCELERATE
      const auto rows = left.size();
      const auto inner = right.size();
      const auto columns = right.front().size();
      auto destination = accelerate_left_.begin();
      for (const auto& row : left) destination = std::copy(row.begin(), row.end(), destination);
      cblas_sgemm(CblasRowMajor, CblasNoTrans, CblasNoTrans, static_cast<int>(rows),
                  static_cast<int>(columns), static_cast<int>(inner), 1.0F,
                  accelerate_left_.data(), static_cast<int>(inner),
                  flat_weights_[layer_index].data(), static_cast<int>(columns), 0.0F,
                  accelerate_output_.data(), static_cast<int>(columns));
      for (std::size_t row = 0; row < rows; ++row) {
        std::copy_n(
            accelerate_output_.begin() + static_cast<std::ptrdiff_t>(row * columns), columns,
            output[row].begin());
      }
#endif
    } else {
      matmul_into(left, right, output);
    }
  }

  std::vector<float> mean_;
  std::vector<float> scale_;
  std::vector<Matrix> weights_;
  std::vector<std::vector<float>> flat_weights_;
  std::vector<std::vector<float>> biases_;
  Matrix normalized_;
  Matrix hidden_one_;
  Matrix hidden_two_;
  Matrix logit_matrix_;
  std::vector<float> logits_;
  std::vector<float> scores_;
  std::vector<float> accelerate_left_;
  std::vector<float> accelerate_output_;
  std::string backend_;
  std::size_t block_size_;
  std::size_t worker_count_;
  std::mutex workspace_mutex_;
};

}  // namespace

PYBIND11_MODULE(_native_runtime, module) {
  module.doc() = "RoverEdge fresh naive FP32 runtime";
  module.def("naive_matmul", &matmul, py::arg("left"), py::arg("right"));
  module.def("blocked_matmul", &blocked_matmul, py::arg("left"), py::arg("right"),
             py::arg("block_size"));
  module.def("accelerate_matmul", &accelerate_matmul, py::arg("left"), py::arg("right"));
  module.def("parallel_blocked_matmul", &parallel_blocked_matmul, py::arg("left"),
             py::arg("right"), py::arg("block_size"), py::arg("worker_count"));
  module.def("accelerate_available", [] { return ROVEREDGE_HAS_ACCELERATE != 0; });
  module.def("runtime_metadata", [](const std::string& backend, std::size_t block_size,
                                    std::size_t worker_count) {
    py::dict metadata;
    metadata["compiler"] = __VERSION__;
    metadata["cxx_standard"] = "C++20";
    metadata["kernel"] = backend == "native-accelerate"
                             ? "apple-accelerate-cblas-sgemm"
                         : backend == "native-parallel-blocked"
                             ? "fresh-parallel-blocked-fp32-v1"
                         : backend == "native-blocked" ? "fresh-blocked-fp32-v1"
                                                       : "fresh-naive-fp32-v1";
    metadata["block_size"] = std::to_string(block_size);
    metadata["worker_count"] = std::to_string(worker_count);
    metadata["accelerate_available"] = ROVEREDGE_HAS_ACCELERATE ? "true" : "false";
    return metadata;
  }, py::arg("backend"), py::arg("block_size"), py::arg("worker_count"));
  py::class_<NativeRiskModel>(module, "NativeRiskModel")
      .def(py::init<std::vector<float>, std::vector<float>, std::vector<Matrix>,
                    std::vector<std::vector<float>>, std::string, std::size_t,
                    std::size_t>(),
           py::arg("mean"), py::arg("scale"), py::arg("weights"), py::arg("biases"),
           py::arg("backend") = "native-naive", py::arg("block_size") = 16,
           py::arg("worker_count") = 1)
      .def("evaluate", &NativeRiskModel::evaluate, py::call_guard<py::gil_scoped_release>());
}
