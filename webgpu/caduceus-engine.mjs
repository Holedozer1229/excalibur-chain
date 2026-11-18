const DENSE_SHADER = /* wgsl */ `
struct Dimensions {
  input_size: u32,
  output_size: u32,
  _padding0: u32,
  _padding1: u32,
}

@group(0) @binding(0) var<storage, read> input_values: array<f32>;
@group(0) @binding(1) var<storage, read> packed_weights: array<u32>;
@group(0) @binding(2) var<storage, read> output_scales: array<f32>;
@group(0) @binding(3) var<storage, read> biases: array<f32>;
@group(0) @binding(4) var<storage, read_write> output_values: array<f32>;
@group(0) @binding(5) var<uniform> dims: Dimensions;

fn signed_weight(index: u32) -> f32 {
  let word = packed_weights[index / 4u];
  let shift = (index % 4u) * 8u;
  let byte_value = (word >> shift) & 255u;
  var value = i32(byte_value);
  if (value >= 128) {
    value -= 256;
  }
  return f32(value);
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
  let output_index = id.x;
  if (output_index >= dims.output_size) {
    return;
  }

  var sum = 0.0;
  let weight_base = output_index * dims.input_size;
  for (var input_index = 0u; input_index < dims.input_size; input_index += 1u) {
    sum += input_values[input_index]
      * signed_weight(weight_base + input_index);
  }
  output_values[output_index] =
    sum * output_scales[output_index] + biases[output_index];
}
`;

export function packInt8Weights(weights) {
  if (!(weights instanceof Int8Array) || weights.length === 0) {
    throw new TypeError("weights must be a non-empty Int8Array");
  }

  const packed = new Uint32Array(Math.ceil(weights.length / 4));
  for (let i = 0; i < weights.length; i += 1) {
    packed[i >>> 2] |= (weights[i] & 0xff) << ((i & 3) * 8);
  }
  return packed;
}

export class CaduceusWebGPU {
  static async create(options = {}) {
    if (!globalThis.navigator?.gpu) {
      throw new Error("WebGPU is unavailable in this browser.");
    }

    const adapter = await navigator.gpu.requestAdapter(options.adapterOptions);
    if (!adapter) {
      throw new Error("No compatible WebGPU adapter is available.");
    }
    const device = await adapter.requestDevice(options.deviceDescriptor);
    return new CaduceusWebGPU(device);
  }

  constructor(device) {
    if (!device) {
      throw new TypeError("A WebGPU device is required.");
    }
    this.device = device;
    this.pipeline = device.createComputePipeline({
      layout: "auto",
      compute: {
        module: device.createShaderModule({ code: DENSE_SHADER }),
        entryPoint: "main",
      },
    });
  }

  async denseInt8(input, weights, outputSize, scales, biases = null) {
    if (!(input instanceof Float32Array) || input.length === 0) {
      throw new TypeError("input must be a non-empty Float32Array");
    }
    if (!Number.isInteger(outputSize) || outputSize < 1) {
      throw new RangeError("outputSize must be a positive integer");
    }
    if (!(weights instanceof Int8Array) || weights.length !== input.length * outputSize) {
      throw new RangeError("weights must contain outputSize * inputSize int8 values");
    }
    if (!(scales instanceof Float32Array) || scales.length !== outputSize) {
      throw new RangeError("scales must contain one Float32 value per output");
    }
    if (biases === null) {
      biases = new Float32Array(outputSize);
    }
    if (!(biases instanceof Float32Array) || biases.length !== outputSize) {
      throw new RangeError("biases must contain one Float32 value per output");
    }

    const packed = packInt8Weights(weights);
    const dimsData = new Uint32Array([input.length, outputSize, 0, 0]);
    const inputBuffer = this.#buffer(input);
    const weightsBuffer = this.#buffer(packed);
    const scalesBuffer = this.#buffer(scales);
    const biasesBuffer = this.#buffer(biases);
    const dimensionsBuffer = this.device.createBuffer({
      size: dimsData.byteLength,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });
    const outputBuffer = this.device.createBuffer({
      size: outputSize * Float32Array.BYTES_PER_ELEMENT,
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC,
    });
    const readbackBuffer = this.device.createBuffer({
      size: outputSize * Float32Array.BYTES_PER_ELEMENT,
      usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST,
    });

    let mapped = false;
    try {
      this.device.queue.writeBuffer(dimensionsBuffer, 0, dimsData);
      const bindGroup = this.device.createBindGroup({
        layout: this.pipeline.getBindGroupLayout(0),
        entries: [
          { binding: 0, resource: { buffer: inputBuffer } },
          { binding: 1, resource: { buffer: weightsBuffer } },
          { binding: 2, resource: { buffer: scalesBuffer } },
          { binding: 3, resource: { buffer: biasesBuffer } },
          { binding: 4, resource: { buffer: outputBuffer } },
          { binding: 5, resource: { buffer: dimensionsBuffer } },
        ],
      });

      const encoder = this.device.createCommandEncoder();
      const pass = encoder.beginComputePass();
      pass.setPipeline(this.pipeline);
      pass.setBindGroup(0, bindGroup);
      pass.dispatchWorkgroups(Math.ceil(outputSize / 64));
      pass.end();
      encoder.copyBufferToBuffer(
        outputBuffer, 0, readbackBuffer, 0,
        outputSize * Float32Array.BYTES_PER_ELEMENT,
      );
      this.device.queue.submit([encoder.finish()]);

      await readbackBuffer.mapAsync(GPUMapMode.READ);
      mapped = true;
      return new Float32Array(readbackBuffer.getMappedRange().slice(0));
    } finally {
      if (mapped) {
        readbackBuffer.unmap();
      }
      inputBuffer.destroy();
      weightsBuffer.destroy();
      scalesBuffer.destroy();
      biasesBuffer.destroy();
      dimensionsBuffer.destroy();
      outputBuffer.destroy();
      readbackBuffer.destroy();
    }
  }

  destroy() {
    this.device.destroy();
  }

  #buffer(data) {
    const buffer = this.device.createBuffer({
      size: Math.max(4, data.byteLength),
      usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
    });
    this.device.queue.writeBuffer(buffer, 0, data);
    return buffer;
  }
}
